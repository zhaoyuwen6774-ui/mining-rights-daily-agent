from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack
from types import TracebackType
from typing import Any, Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_MODULES = {
    "news": "mining_rights_agent.news.server",
    "pdf": "mining_rights_agent.pdf.server",
    "price": "mining_rights_agent.price.server",
}


class ToolGateway(Protocol):
    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class McpProcessGateway:
    def __init__(self) -> None:
        self._stack: AsyncExitStack | None = None
        self._sessions: dict[str, ClientSession] = {}

    async def __aenter__(self) -> McpProcessGateway:
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        environment = os.environ.copy()
        for name, module in SERVER_MODULES.items():
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", module],
                env=environment,
            )
            read_stream, write_stream = await self._stack.enter_async_context(
                stdio_client(parameters)
            )
            session = await self._stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()
            self._sessions[name] = session
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._stack is not None:
            await self._stack.__aexit__(exc_type, exc_value, traceback)

    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if server not in self._sessions:
            raise RuntimeError(f"MCP server is not connected: {server}")
        result = await self._sessions[server].call_tool(tool, arguments=arguments)
        if result.isError:
            message = " ".join(
                str(getattr(content, "text", "")) for content in result.content
            ).strip()
            raise RuntimeError(message or f"MCP tool failed: {server}.{tool}")

        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict):
            return structured
        text_parts = [
            str(getattr(content, "text", ""))
            for content in result.content
            if getattr(content, "type", None) == "text"
        ]
        if not text_parts:
            raise ValueError(f"MCP tool returned no JSON content: {server}.{tool}")
        payload = json.loads("".join(text_parts))
        if not isinstance(payload, dict):
            raise ValueError(f"MCP tool returned a non-object payload: {server}.{tool}")
        return payload
