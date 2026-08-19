from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from mining_rights_agent.agent.gateway import ToolGateway
from mining_rights_agent.agent.intent import parse_intent
from mining_rights_agent.agent.llm import OptionalLlmPolisher
from mining_rights_agent.common.models import (
    Article,
    NewsItem,
    PriceTrend,
    ReportCandidate,
    ResourceRecord,
    ToolResult,
)
from mining_rights_agent.common.settings import Settings


@dataclass
class BriefEvidence:
    request: str
    generated_at: datetime
    project: str
    company: str | None
    commodity: str
    news: list[NewsItem]
    articles: dict[str, Article]
    reports: list[ReportCandidate]
    resources: list[ResourceRecord]
    price: PriceTrend | None
    warnings: list[str]


class BriefOrchestrator:
    def __init__(self, gateway: ToolGateway, settings: Settings) -> None:
        self._gateway = gateway
        self._polisher = OptionalLlmPolisher(settings)

    async def collect(self, request: str, pdf_url: str | None = None) -> BriefEvidence:
        intent = parse_intent(request)
        search_query = " ".join(
            value for value in [intent.project, intent.company, intent.commodity] if value
        )
        news_call = self._gateway.call(
            "news", "search", {"query": search_query, "days": intent.days}
        )
        report_call = self._gateway.call("pdf", "find_reports", {"project": intent.project})
        price_call = self._gateway.call(
            "price", "get_trend", {"commodity": intent.commodity, "days": max(2, intent.days)}
        )
        news_raw, reports_raw, price_raw = await asyncio.gather(news_call, report_call, price_call)
        news_result = ToolResult[list[NewsItem]].model_validate(news_raw)
        reports_result = ToolResult[list[ReportCandidate]].model_validate(reports_raw)
        price_result = ToolResult[PriceTrend | None].model_validate(price_raw)

        selected_news = news_result.data[:5]
        article_calls = [
            self._gateway.call("news", "fetch_article", {"url": str(item.url)})
            for item in selected_news[:3]
        ]
        article_results = await asyncio.gather(*article_calls, return_exceptions=True)
        articles: dict[str, Article] = {}
        warnings = [
            *news_result.warnings,
            *reports_result.warnings,
            *price_result.warnings,
        ]
        for item, raw in zip(selected_news[:3], article_results, strict=True):
            if isinstance(raw, BaseException):
                warnings.append(f"Article fetch failed: {item.title}")
                continue
            result = ToolResult[Article | None].model_validate(raw)
            warnings.extend(result.warnings)
            if result.data:
                articles[str(item.url)] = result.data

        resources: list[ResourceRecord] = []
        selected_pdf_url = pdf_url or (reports_result.data[0].url if reports_result.data else None)
        if selected_pdf_url:
            resources_raw = await self._gateway.call(
                "pdf", "extract_resources", {"pdf_url": selected_pdf_url}
            )
            resources_result = ToolResult[list[ResourceRecord]].model_validate(resources_raw)
            resources = resources_result.data
            warnings.extend(resources_result.warnings)
        else:
            warnings.append("No technical report was available for resource extraction.")

        return BriefEvidence(
            request=request,
            generated_at=datetime.now(UTC),
            project=intent.project,
            company=intent.company,
            commodity=intent.commodity,
            news=selected_news,
            articles=articles,
            reports=reports_result.data,
            resources=resources,
            price=price_result.data,
            warnings=list(dict.fromkeys(warnings)),
        )

    async def generate(self, request: str, pdf_url: str | None = None) -> str:
        evidence = await self.collect(request, pdf_url)
        conclusion = self._deterministic_conclusion(evidence)
        allowed_citations = self._allowed_citations(evidence)
        llm_evidence = self._conclusion_evidence(evidence)
        try:
            polished = await self._polisher.conclusion(llm_evidence, allowed_citations)
        except Exception:
            polished = None
            evidence.warnings.append("LLM polishing failed; deterministic conclusion was used.")
        return render_markdown(evidence, polished or conclusion)

    @staticmethod
    def _allowed_citations(evidence: BriefEvidence) -> set[str]:
        citations = {f"[N{index}]" for index in range(1, len(evidence.news) + 1)}
        if evidence.resources:
            citations.add("[R1]")
        if evidence.price and evidence.price.points:
            citations.add("[P1]")
        return citations

    @staticmethod
    def _conclusion_evidence(evidence: BriefEvidence) -> str:
        lines = [f"Project: {evidence.project}", f"Commodity: {evidence.commodity}"]
        lines.extend(
            f"[N{index}] {item.title}: {item.summary}"
            for index, item in enumerate(evidence.news[:3], start=1)
        )
        if evidence.resources:
            lines.append(
                f"[R1] Extracted {len(evidence.resources)} Indicated/Inferred resource rows."
            )
        if evidence.price and evidence.price.change_percent is not None:
            lines.append(
                f"[P1] LME {evidence.commodity} changed "
                f"{evidence.price.change_percent:+.2f}% over the available period."
            )
        return "\n".join(lines)

    @staticmethod
    def _deterministic_conclusion(evidence: BriefEvidence) -> str:
        parts: list[str] = []
        if evidence.news:
            parts.append(f"近期动态以“{evidence.news[0].title}”为首要信号 [N1]。")
        if evidence.resources:
            parts.append(f"技术报告中识别到 {len(evidence.resources)} 条资源量记录 [R1]。")
        if evidence.price and evidence.price.change_percent is not None:
            parts.append(
                f"可用区间内 LME {evidence.commodity} 价格变动"
                f" {evidence.price.change_percent:+.2f}% [P1]。"
            )
        if not parts:
            return "当前可验证证据不足，建议补充技术报告或授权行情数据后再作判断。"
        return "".join(parts)


def _source_link(url: str, label: str) -> str:
    return f"[{label}]({url})" if url.startswith("https://") else f"{label} (`{url}`)"


def render_markdown(evidence: BriefEvidence, conclusion: str) -> str:
    lines = [
        f"# {evidence.project} 矿权日报",
        "",
        f"> 生成时间：{evidence.generated_at.astimezone().strftime('%Y-%m-%d %H:%M %Z')}",
        f"> 查询：{evidence.request}",
        "",
        "## 今日结论",
        "",
        conclusion,
        "",
        "## 新闻动态",
        "",
    ]
    if evidence.news:
        for index, item in enumerate(evidence.news, start=1):
            summary = item.summary.strip()
            if article := evidence.articles.get(str(item.url)):
                summary = article.text.strip().split("\n", 1)[0][:300]
            published = item.published_at.date().isoformat() if item.published_at else "日期未知"
            lines.extend(
                [
                    f"### {index}. {item.title} [N{index}]",
                    "",
                    f"{summary or '正文摘要不可用。'}",
                    "",
                    f"来源：{item.source_name}，{published}",
                    "",
                ]
            )
    else:
        lines.extend(["未检索到符合条件的近期新闻。", ""])

    lines.extend(["## 资源量", ""])
    if evidence.resources:
        lines.extend(
            [
                "| 分类 | 矿石量 (Mt) | 品位 | 金属量 | 报告准则 | 页码 |",
                "|---|---:|---:|---:|---|---:|",
            ]
        )
        for record in evidence.resources:
            metal = (
                f"{record.contained_metal:,.2f} {record.metal_unit}"
                if record.contained_metal is not None
                else "未披露"
            )
            lines.append(
                f"| {record.classification} | {record.tonnage_mt:,.2f} | "
                f"{record.grade_value:,.3f} {record.grade_unit} | {metal} | "
                f"{record.reporting_code} | {record.source_page} [R1] |"
            )
        lines.append("")
    else:
        lines.extend(["未获得可验证的 Indicated/Inferred 资源量数据。", ""])

    lines.extend(["## 价格走势", ""])
    if evidence.price and evidence.price.points:
        first = evidence.price.points[0]
        last = evidence.price.points[-1]
        lines.extend(
            [
                f"LME {evidence.price.commodity} 从 {first.date} 的 "
                f"{first.price:,.2f} {first.currency}/{first.unit} 变动至 "
                f"{last.date} 的 {last.price:,.2f} {last.currency}/{last.unit}，"
                f"区间变化 {evidence.price.change_percent:+.2f}% [P1]。",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "没有可用的对应 LME 行情。系统未使用其他交易所或代理品种替代。",
                "",
            ]
        )

    lines.extend(["## 风险提示", ""])
    risks = list(evidence.warnings)
    if evidence.commodity == "lithium":
        risks.append("LME 不挂牌锂，本简报不提供伪造或替代的 LME 锂价。")
    if not risks:
        risks.append("外部数据可能延迟，交易或投资决策前应回查原始来源。")
    lines.extend(f"- {risk}" for risk in dict.fromkeys(risks))

    lines.extend(["", "## 引用来源", ""])
    for index, item in enumerate(evidence.news, start=1):
        lines.append(f"- [N{index}] {_source_link(str(item.url), item.title)}")
    if evidence.resources:
        report_url = evidence.resources[0].source_url
        report_title = evidence.reports[0].title if evidence.reports else "Technical report PDF"
        lines.append(f"- [R1] {_source_link(report_url, report_title)}")
    if evidence.price and evidence.price.points:
        point = evidence.price.points[-1]
        lines.append(f"- [P1] {_source_link(point.source_url, point.price_type)}")
    lines.append("")
    return "\n".join(lines)
