from __future__ import annotations

from _pytest.monkeypatch import MonkeyPatch

from mining_rights_agent.agent.gateway import McpProcessGateway


async def test_real_mcp_stdio_roundtrip(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_MODE", "fixture")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    async with McpProcessGateway() as gateway:
        result = await gateway.call("news", "search", {"query": "Pilbara lithium", "days": 7})
        resources = await gateway.call(
            "pdf",
            "extract_resources",
            {"pdf_url": "fixture://pilbara-resource-statement"},
        )
        price = await gateway.call("price", "get_trend", {"commodity": "copper", "days": 7})

    assert result["status"] == "ok"
    assert len(result["data"]) == 3
    assert len(resources["data"]) == 2
    assert price["data"]["commodity"] == "copper"
