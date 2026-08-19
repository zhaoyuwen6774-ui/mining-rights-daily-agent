from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from time import struct_time
from typing import Any, cast
from urllib.parse import urlparse

import feedparser
import trafilatura

from mining_rights_agent.common.cache import SqliteCache
from mining_rights_agent.common.http import SafeHttpClient
from mining_rights_agent.common.models import Article, NewsItem, SourceRef, Status, ToolResult
from mining_rights_agent.common.settings import Settings

LOGGER = logging.getLogger(__name__)
TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _feed_datetime(value: struct_time | None) -> datetime | None:
    if value is None:
        return None
    return datetime(*value[:6], tzinfo=UTC)


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in TOKEN_PATTERN.findall(value) if len(token) > 1}


def _relevance(query: str, title: str, summary: str) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.5
    text_tokens = _tokens(f"{title} {summary}")
    matched = len(query_tokens & text_tokens)
    return min(1.0, matched / len(query_tokens))


class NewsService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache = SqliteCache(settings.cache_dir / "news.sqlite3")
        self._http = SafeHttpClient(
            settings.http_timeout_seconds,
            settings.http_max_bytes,
            settings.http_user_agent,
        )

    def _load_fixtures(self) -> list[dict[str, Any]]:
        payload: object = json.loads(self._settings.news_fixture_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("news fixtures must be a JSON array")
        return cast(list[dict[str, Any]], payload)

    async def search(self, query: str, days: int) -> ToolResult[list[NewsItem]]:
        if days < 1 or days > 90:
            raise ValueError("days must be between 1 and 90")
        if self._settings.app_mode == "fixture":
            return self._search_fixtures(query, days)

        cache_key = hashlib.sha256(f"search:{query}:{days}".encode()).hexdigest()
        if cached := self._cache.get(cache_key):
            return ToolResult[list[NewsItem]].model_validate(cached)

        outcomes = await asyncio.gather(
            *(self._search_feed(url, query, days) for url in self._settings.feed_urls),
            return_exceptions=True,
        )
        items: dict[str, NewsItem] = {}
        warnings: list[str] = []
        sources: list[SourceRef] = []
        accessed_at = datetime.now(UTC)
        for feed_url, outcome in zip(self._settings.feed_urls, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                LOGGER.warning("news feed failed", extra={"feed_url": feed_url}, exc_info=outcome)
                warnings.append(f"Feed unavailable: {feed_url}")
                continue
            feed_items, feed_title = outcome
            for item in feed_items:
                items[str(item.url)] = item
            sources.append(SourceRef(title=feed_title, url=feed_url, accessed_at=accessed_at))

        ordered = sorted(
            items.values(),
            key=lambda item: (
                item.relevance_score,
                item.published_at or datetime.min.replace(tzinfo=UTC),
            ),
            reverse=True,
        )
        status = Status.OK if not warnings else (Status.PARTIAL if ordered else Status.UNAVAILABLE)
        result = ToolResult[list[NewsItem]](
            status=status,
            data=ordered[:20],
            sources=sources,
            as_of=accessed_at,
            warnings=warnings,
        )
        self._cache.set(
            cache_key,
            result.model_dump(mode="json"),
            self._settings.news_cache_ttl_seconds,
        )
        return result

    async def _search_feed(
        self, feed_url: str, query: str, days: int
    ) -> tuple[list[NewsItem], str]:
        response = await self._http.get(
            feed_url,
            allowed_hosts=self._settings.allowed_news_hosts,
            allowed_content_types={
                "application/rss+xml",
                "application/xml",
                "text/xml",
                "application/atom+xml",
                "text/html",
            },
        )
        parsed = feedparser.parse(response.content)
        if parsed.bozo and not parsed.entries:
            raise ValueError(f"invalid feed: {feed_url}")

        cutoff = datetime.now(UTC) - timedelta(days=days)
        source_name = str(parsed.feed.get("title") or urlparse(feed_url).hostname or "RSS")
        items: list[NewsItem] = []
        for entry in parsed.entries:
            title = str(entry.get("title", "")).strip()
            url = str(entry.get("link", "")).strip()
            summary = str(entry.get("summary", "")).strip()
            published_at = _feed_datetime(
                entry.get("published_parsed") or entry.get("updated_parsed")
            )
            score = _relevance(query, title, summary)
            if not title or not url or score == 0:
                continue
            if published_at is not None and published_at < cutoff:
                continue
            items.append(
                NewsItem.model_validate(
                    {
                        "title": title,
                        "url": url,
                        "published_at": published_at,
                        "summary": re.sub(r"<[^>]+>", " ", summary).strip(),
                        "source_name": source_name,
                        "relevance_score": score,
                    }
                )
            )
        return items, source_name

    def _search_fixtures(self, query: str, days: int) -> ToolResult[list[NewsItem]]:
        now = datetime.now(UTC)
        fixtures = self._load_fixtures()
        fixture_dates = [
            datetime.fromisoformat(str(raw["published_at"]).replace("Z", "+00:00"))
            for raw in fixtures
        ]
        cutoff = max(fixture_dates) - timedelta(days=days)
        items: list[NewsItem] = []
        for raw in fixtures:
            published_at = datetime.fromisoformat(str(raw["published_at"]).replace("Z", "+00:00"))
            score = _relevance(query, str(raw["title"]), str(raw["summary"]))
            if published_at >= cutoff and score > 0:
                items.append(
                    NewsItem.model_validate(
                        {
                            "title": raw["title"],
                            "url": raw["url"],
                            "published_at": published_at,
                            "summary": raw["summary"],
                            "source_name": raw["source_name"],
                            "relevance_score": score,
                        }
                    )
                )
        items.sort(key=lambda item: (item.relevance_score, item.published_at), reverse=True)
        return ToolResult[list[NewsItem]](
            status=Status.OK,
            data=items,
            sources=[
                SourceRef(title="Bundled news fixtures", url="fixture://news", accessed_at=now)
            ],
            as_of=now,
            warnings=["Fixture mode is enabled; news is not live."],
        )

    async def fetch_article(self, url: str) -> ToolResult[Article | None]:
        now = datetime.now(UTC)
        if self._settings.app_mode == "fixture":
            for raw in self._load_fixtures():
                if str(raw["url"]) == url:
                    article = Article.model_validate(
                        {
                            "title": raw["title"],
                            "url": url,
                            "text": raw["content"],
                            "published_at": datetime.fromisoformat(
                                str(raw["published_at"]).replace("Z", "+00:00")
                            ),
                            "author": raw.get("author"),
                        }
                    )
                    return ToolResult[Article | None](
                        status=Status.OK,
                        data=article,
                        sources=[SourceRef(title=article.title, url=url, accessed_at=now)],
                        as_of=now,
                        warnings=["Fixture mode is enabled; article content is bundled test data."],
                    )
            return ToolResult[Article | None](
                status=Status.UNAVAILABLE,
                data=None,
                as_of=now,
                warnings=["Article URL was not found in fixtures."],
            )

        response = await self._http.get(
            url,
            allowed_hosts=self._settings.allowed_news_hosts,
            allowed_content_types={"text/html", "application/xhtml+xml"},
        )
        html = response.content.decode("utf-8", errors="replace")
        extracted = trafilatura.extract(
            html,
            url=response.url,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        if not extracted:
            return ToolResult[Article | None](
                status=Status.UNAVAILABLE,
                data=None,
                as_of=now,
                warnings=["Article body could not be extracted."],
            )
        article = Article.model_validate(
            {"title": response.url, "url": response.url, "text": extracted}
        )
        return ToolResult[Article | None](
            status=Status.OK,
            data=article,
            sources=[SourceRef(title=article.title, url=response.url, accessed_at=now)],
            as_of=now,
        )
