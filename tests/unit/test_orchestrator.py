from __future__ import annotations

from typing import Any

from mining_rights_agent.agent.orchestrator import BriefOrchestrator
from mining_rights_agent.common.settings import Settings
from mining_rights_agent.news.service import NewsService
from mining_rights_agent.pdf.service import MineralPdfService
from mining_rights_agent.price.service import LmePriceService


class FixtureGateway:
    def __init__(self, settings: Settings) -> None:
        self.news = NewsService(settings)
        self.pdf = MineralPdfService(settings)
        self.price = LmePriceService(settings)

    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if (server, tool) == ("news", "search"):
            result = await self.news.search(str(arguments["query"]), int(arguments["days"]))
        elif (server, tool) == ("news", "fetch_article"):
            result = await self.news.fetch_article(str(arguments["url"]))
        elif (server, tool) == ("pdf", "find_reports"):
            result = self.pdf.find_reports(str(arguments["project"]))
        elif (server, tool) == ("pdf", "extract_resources"):
            result = await self.pdf.extract_resources(str(arguments["pdf_url"]))
        elif (server, tool) == ("price", "get_trend"):
            result = await self.price.get_trend(str(arguments["commodity"]), int(arguments["days"]))
        else:
            raise AssertionError(f"unexpected tool call: {server}.{tool}")
        return result.model_dump(mode="json")


async def test_generates_cited_pilbara_brief(fixture_settings: Settings) -> None:
    orchestrator = BriefOrchestrator(FixtureGateway(fixture_settings), fixture_settings)

    markdown = await orchestrator.generate("给我生成一份关于 Pilbara 锂矿的今日简报")

    assert "# Pilbara 矿权日报" in markdown
    assert "[N1]" in markdown
    assert "[R1]" in markdown
    assert "LME 不挂牌锂" in markdown
    assert "fixture://pilbara-resource-statement" in markdown
