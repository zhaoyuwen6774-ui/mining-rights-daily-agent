from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Settings as FastMcpSettings

McpLogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def create_mcp_server(name: str, log_level: McpLogLevel) -> FastMCP:
    # MCP 1.29 leaves the generic lifespan annotation unresolved until rebuilt.
    FastMcpSettings.model_rebuild()
    return FastMCP(name, log_level=log_level)

