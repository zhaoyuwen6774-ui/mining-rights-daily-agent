from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlencode

from mining_rights_agent.common.cache import SqliteCache
from mining_rights_agent.common.http import SafeHttpClient
from mining_rights_agent.common.models import PricePoint, PriceTrend, SourceRef, Status, ToolResult
from mining_rights_agent.common.settings import Settings

LME_COMMODITIES = {"copper", "zinc", "nickel"}


class LmePriceService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache = SqliteCache(settings.cache_dir / "prices.sqlite3")
        self._http = SafeHttpClient(
            settings.http_timeout_seconds,
            settings.http_max_bytes,
            settings.http_user_agent,
        )

    def _unsupported(self, commodity: str) -> str | None:
        normalized = commodity.casefold().strip()
        if normalized not in LME_COMMODITIES:
            return (
                f"{commodity} is not supported by this LME service. "
                "Only copper, zinc, and nickel are exposed; no proxy price is substituted."
            )
        return None

    def _fixture_points(self, commodity: str) -> list[PricePoint]:
        payload = json.loads(self._settings.price_fixture_path.read_text(encoding="utf-8"))
        return [
            PricePoint.model_validate(item)
            for item in payload
            if str(item["commodity"]).casefold() == commodity.casefold()
        ]

    async def _live_points(self, commodity: str, start: date, end: date) -> list[PricePoint]:
        if not self._settings.lme_provider_url:
            raise RuntimeError(
                "LME_PROVIDER_URL is not configured. "
                "A licensed or authorized LME data endpoint is required."
            )
        query = urlencode(
            {"commodity": commodity, "start": start.isoformat(), "end": end.isoformat()}
        )
        url = f"{self._settings.lme_provider_url.rstrip('/')}?{query}"
        headers = (
            {"Authorization": f"Bearer {self._settings.lme_api_key}"}
            if self._settings.lme_api_key
            else None
        )
        response = await self._http.get(
            url,
            allowed_content_types={"application/json", "text/json"},
            headers=headers,
        )
        payload = json.loads(response.content)
        raw_points = payload.get("data", []) if isinstance(payload, dict) else payload
        points: list[PricePoint] = []
        for raw in raw_points:
            points.append(
                PricePoint(
                    commodity=commodity,
                    date=date.fromisoformat(str(raw["date"])[:10]),
                    price=float(raw.get("price", raw.get("value"))),
                    currency=str(raw.get("currency", "USD")),
                    unit=str(raw.get("unit", "tonne")),
                    price_type=str(raw.get("price_type", "LME official cash")),
                    source_url=str(raw.get("source_url", response.url)),
                    provider=str(raw.get("provider", "configured-lme-provider")),
                )
            )
        return sorted(points, key=lambda point: point.date)

    async def _points(self, commodity: str, start: date, end: date) -> list[PricePoint]:
        if self._settings.app_mode == "fixture":
            points = self._fixture_points(commodity)
            return [point for point in points if start <= point.date <= end]
        return await self._live_points(commodity, start, end)

    async def get_price(
        self, commodity: str, requested_date: date
    ) -> ToolResult[PricePoint | None]:
        now = datetime.now(UTC)
        if warning := self._unsupported(commodity):
            return ToolResult[PricePoint | None](
                status=Status.UNAVAILABLE, data=None, as_of=now, warnings=[warning]
            )
        try:
            points = await self._points(commodity, requested_date, requested_date)
        except Exception as exc:
            return ToolResult[PricePoint | None](
                status=Status.UNAVAILABLE,
                data=None,
                as_of=now,
                warnings=[str(exc)],
            )
        point = points[0] if points else None
        warnings = [] if point else ["No LME price was available for the requested date."]
        if self._settings.app_mode == "fixture":
            warnings.append("Fixture mode is enabled; prices are bundled test data.")
        return ToolResult[PricePoint | None](
            status=Status.OK if point else Status.UNAVAILABLE,
            data=point,
            sources=(
                [SourceRef(title=point.price_type, url=point.source_url, accessed_at=now)]
                if point
                else []
            ),
            as_of=now,
            warnings=warnings,
        )

    async def get_trend(self, commodity: str, days: int) -> ToolResult[PriceTrend | None]:
        if days < 2 or days > 90:
            raise ValueError("days must be between 2 and 90")
        now = datetime.now(UTC)
        if warning := self._unsupported(commodity):
            return ToolResult[PriceTrend | None](
                status=Status.UNAVAILABLE, data=None, as_of=now, warnings=[warning]
            )

        cache_key = hashlib.sha256(f"trend:{commodity}:{days}".encode()).hexdigest()
        if cached := self._cache.get(cache_key):
            return ToolResult[PriceTrend | None].model_validate(cached)

        if self._settings.app_mode == "fixture":
            all_fixture_points = self._fixture_points(commodity)
            end = max((point.date for point in all_fixture_points), default=now.date())
        else:
            end = now.date()
        start = end - timedelta(days=days - 1)
        try:
            points = await self._points(commodity, start, end)
        except Exception as exc:
            return ToolResult[PriceTrend | None](
                status=Status.UNAVAILABLE,
                data=None,
                as_of=now,
                warnings=[str(exc)],
            )
        trend: PriceTrend | None = None
        if points:
            first = points[0].price
            last = points[-1].price
            trend = PriceTrend(
                commodity=commodity,
                points=points,
                change_absolute=round(last - first, 4),
                change_percent=round((last - first) / first * 100, 4),
            )
        warnings: list[str] = []
        if not points:
            warnings.append("No LME prices were available for the requested range.")
        if self._settings.app_mode == "fixture":
            warnings.append("Fixture mode is enabled; prices are bundled test data.")
        result = ToolResult[PriceTrend | None](
            status=Status.OK if trend else Status.UNAVAILABLE,
            data=trend,
            sources=(
                [
                    SourceRef(
                        title=f"{commodity.title()} {points[-1].price_type}",
                        url=points[-1].source_url,
                        accessed_at=now,
                    )
                ]
                if points
                else []
            ),
            as_of=now,
            warnings=warnings,
        )
        self._cache.set(
            cache_key,
            result.model_dump(mode="json"),
            self._settings.price_cache_ttl_seconds,
        )
        return result
