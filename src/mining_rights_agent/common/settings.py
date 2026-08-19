from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(Path.cwd()))).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_mode: Literal["live", "fixture"] = "live"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    data_dir: Path = Field(default=PROJECT_ROOT / "data")
    cache_dir: Path = Field(default=PROJECT_ROOT / "data" / "cache")

    http_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    http_max_bytes: int = Field(default=25_000_000, gt=0)
    http_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Apple Silicon Mac OS X) "
        "AppleWebKit/537.36 Chrome/140 Safari/537.36 "
        "MiningRightsDailyAgent/0.1"
    )

    news_feed_urls: str = (
        "https://www.mining.com/feed/"
        ",https://www.spglobal.com/marketintelligence/en/news-insights/latest-news-headlines/rss"
    )
    news_allowed_hosts: str = "mining.com,www.mining.com,spglobal.com,www.spglobal.com"
    news_cache_ttl_seconds: int = Field(default=900, ge=0)
    news_fixture_path: Path = Field(default=PROJECT_ROOT / "data" / "fixtures" / "news.json")

    report_registry_path: Path = Field(default=PROJECT_ROOT / "data" / "report_registry.json")
    resource_fixture_path: Path = Field(
        default=PROJECT_ROOT / "data" / "fixtures" / "resources.json"
    )
    pdf_cache_ttl_seconds: int = Field(default=86_400, ge=0)

    lme_provider_url: str | None = None
    lme_api_key: str | None = None
    price_fixture_path: Path = Field(default=PROJECT_ROOT / "data" / "fixtures" / "prices.json")
    price_cache_ttl_seconds: int = Field(default=3600, ge=0)

    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None

    @property
    def feed_urls(self) -> list[str]:
        return [value.strip() for value in self.news_feed_urls.split(",") if value.strip()]

    @property
    def allowed_news_hosts(self) -> set[str]:
        return {
            value.strip().lower() for value in self.news_allowed_hosts.split(",") if value.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
