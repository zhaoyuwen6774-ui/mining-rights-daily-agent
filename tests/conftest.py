from __future__ import annotations

from pathlib import Path

import pytest

from mining_rights_agent.common.settings import PROJECT_ROOT, Settings


@pytest.fixture
def fixture_settings(tmp_path: Path) -> Settings:
    return Settings(
        app_mode="fixture",
        cache_dir=tmp_path / "cache",
        data_dir=PROJECT_ROOT / "data",
        news_fixture_path=PROJECT_ROOT / "data" / "fixtures" / "news.json",
        resource_fixture_path=PROJECT_ROOT / "data" / "fixtures" / "resources.json",
        price_fixture_path=PROJECT_ROOT / "data" / "fixtures" / "prices.json",
        report_registry_path=PROJECT_ROOT / "data" / "report_registry.json",
    )
