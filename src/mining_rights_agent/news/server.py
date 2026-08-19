from __future__ import annotations

import logging
from datetime import UTC, datetime

from mining_rights_agent.common.logging import configure_logging
from mining_rights_agent.common.mcp import create_mcp_server
from mining_rights_agent.common.models import Status, ToolResult
from mining_rights_agent.common.settings import get_settings
from mining_rights_agent.news.service import NewsService

SETTINGS = get_settings()
configure_logging(SETTINGS.log_level)
LOGGER = logging.getLogger(__name__)
SERVICE = NewsService(SETTINGS)
mcp = create_mcp_server("mining-news-mcp", SETTINGS.log_level)


@mcp.tool()
async def search(query: str, days: int = 7) -> dict[str, object]:
    """Search recent mining news and return ranked, source-linked results."""
    try:
        return (await SERVICE.search(query, days)).model_dump(mode="json")
    except Exception as exc:
        LOGGER.exception("news search failed")
        return ToolResult[list[object]](
            status=Status.ERROR,
            data=[],
            as_of=datetime.now(UTC),
            warnings=[f"News search failed: {type(exc).__name__}"],
        ).model_dump(mode="json")


@mcp.tool()
async def fetch_article(url: str) -> dict[str, object]:
    """Fetch and extract the main text of an allow-listed mining news article."""
    try:
        result = await SERVICE.fetch_article(url)
        return result.model_dump(mode="json")
    except Exception as exc:
        LOGGER.exception("article extraction failed")
        return ToolResult[None](
            status=Status.ERROR,
            data=None,
            as_of=datetime.now(UTC),
            warnings=[f"Article extraction failed: {type(exc).__name__}"],
        ).model_dump(mode="json")


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
