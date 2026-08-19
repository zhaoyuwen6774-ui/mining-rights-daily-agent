from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from mining_rights_agent.common.logging import configure_logging
from mining_rights_agent.common.mcp import create_mcp_server
from mining_rights_agent.common.models import Status, ToolResult
from mining_rights_agent.common.settings import get_settings
from mining_rights_agent.price.service import LmePriceService

SETTINGS = get_settings()
configure_logging(SETTINGS.log_level)
LOGGER = logging.getLogger(__name__)
SERVICE = LmePriceService(SETTINGS)
mcp = create_mcp_server("lme-price-mcp", SETTINGS.log_level)


@mcp.tool()
async def get_price(commodity: str, date_value: str) -> dict[str, object]:
    """Return the LME official cash price for a commodity and ISO date."""
    try:
        result = await SERVICE.get_price(commodity, date.fromisoformat(date_value))
        return result.model_dump(mode="json")
    except Exception as exc:
        LOGGER.exception("price lookup failed")
        return ToolResult[None](
            status=Status.ERROR,
            data=None,
            as_of=datetime.now(UTC),
            warnings=[f"Price lookup failed: {type(exc).__name__}"],
        ).model_dump(mode="json")


@mcp.tool()
async def get_trend(commodity: str, days: int = 7) -> dict[str, object]:
    """Return an ordered LME price series and percentage change."""
    try:
        result = await SERVICE.get_trend(commodity, days)
        return result.model_dump(mode="json")
    except Exception as exc:
        LOGGER.exception("price trend failed")
        return ToolResult[None](
            status=Status.ERROR,
            data=None,
            as_of=datetime.now(UTC),
            warnings=[f"Price trend failed: {type(exc).__name__}"],
        ).model_dump(mode="json")


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
