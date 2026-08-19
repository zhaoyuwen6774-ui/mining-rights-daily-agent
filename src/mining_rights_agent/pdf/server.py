from __future__ import annotations

import logging
from datetime import UTC, datetime

from mining_rights_agent.common.logging import configure_logging
from mining_rights_agent.common.mcp import create_mcp_server
from mining_rights_agent.common.models import Status, ToolResult
from mining_rights_agent.common.settings import get_settings
from mining_rights_agent.pdf.service import MineralPdfService

SETTINGS = get_settings()
configure_logging(SETTINGS.log_level)
LOGGER = logging.getLogger(__name__)
SERVICE = MineralPdfService(SETTINGS)
mcp = create_mcp_server("mineral-pdf-mcp", SETTINGS.log_level)


@mcp.tool()
async def find_reports(project: str) -> dict[str, object]:
    """Find curated NI 43-101 or JORC technical reports for a project."""
    try:
        return SERVICE.find_reports(project).model_dump(mode="json")
    except Exception as exc:
        LOGGER.exception("report discovery failed")
        return ToolResult[list[object]](
            status=Status.ERROR,
            data=[],
            as_of=datetime.now(UTC),
            warnings=[f"Report discovery failed: {type(exc).__name__}"],
        ).model_dump(mode="json")


@mcp.tool()
async def extract_resources(pdf_url: str) -> dict[str, object]:
    """Extract Indicated and Inferred resources with page-level provenance."""
    try:
        return (await SERVICE.extract_resources(pdf_url)).model_dump(mode="json")
    except Exception as exc:
        LOGGER.exception("resource extraction failed")
        return ToolResult[list[object]](
            status=Status.ERROR,
            data=[],
            as_of=datetime.now(UTC),
            warnings=[f"Resource extraction failed: {type(exc).__name__}"],
        ).model_dump(mode="json")


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
