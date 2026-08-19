from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, date, datetime
from typing import Any, cast

from mining_rights_agent.common.cache import SqliteCache
from mining_rights_agent.common.http import SafeHttpClient
from mining_rights_agent.common.models import (
    ReportCandidate,
    ResourceRecord,
    SourceRef,
    Status,
    ToolResult,
)
from mining_rights_agent.common.settings import Settings
from mining_rights_agent.pdf.parser import extract_resource_records

LOGGER = logging.getLogger(__name__)


class MineralPdfService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache = SqliteCache(settings.cache_dir / "pdf.sqlite3")
        self._http = SafeHttpClient(
            settings.http_timeout_seconds,
            settings.http_max_bytes,
            settings.http_user_agent,
        )

    def _registry(self) -> list[dict[str, Any]]:
        payload: object = json.loads(
            self._settings.report_registry_path.read_text(encoding="utf-8")
        )
        if not isinstance(payload, list):
            raise ValueError("report registry must be a JSON array")
        return cast(list[dict[str, Any]], payload)

    def find_reports(self, project: str) -> ToolResult[list[ReportCandidate]]:
        now = datetime.now(UTC)
        query = project.casefold().strip()
        candidates: list[ReportCandidate] = []
        for raw in self._registry():
            raw_aliases = raw.get("aliases", [])
            aliases = (
                [str(alias).casefold() for alias in raw_aliases]
                if isinstance(raw_aliases, list)
                else []
            )
            searchable = " ".join([str(raw.get("project", "")).casefold(), *aliases])
            if query not in searchable and not any(alias in query for alias in aliases):
                continue
            if bool(raw.get("fixture")) and self._settings.app_mode != "fixture":
                continue
            published_at = (
                date.fromisoformat(str(raw["published_at"])) if raw.get("published_at") else None
            )
            candidates.append(
                ReportCandidate.model_validate(
                    {
                        "project": raw["project"],
                        "title": raw["title"],
                        "url": raw["url"],
                        "reporting_code": raw.get("reporting_code", "Unknown"),
                        "published_at": published_at,
                    }
                )
            )
        candidates.sort(key=lambda item: item.published_at or date.min, reverse=True)
        status = Status.OK if candidates else Status.UNAVAILABLE
        warnings = [] if candidates else ["No registered technical report matched the project."]
        if self._settings.app_mode == "fixture":
            warnings.append("Fixture mode is enabled; report discovery uses bundled test data.")
        return ToolResult[list[ReportCandidate]](
            status=status,
            data=candidates,
            sources=[
                SourceRef(
                    title="Curated technical report registry",
                    url="local://report-registry",
                    accessed_at=now,
                )
            ],
            as_of=now,
            warnings=warnings,
        )

    def _fixture_resources(self, fixture_url: str) -> list[ResourceRecord]:
        payload = json.loads(self._settings.resource_fixture_path.read_text(encoding="utf-8"))
        return [ResourceRecord.model_validate(item) for item in payload.get(fixture_url, [])]

    async def extract_resources(self, pdf_url: str) -> ToolResult[list[ResourceRecord]]:
        now = datetime.now(UTC)
        if pdf_url.startswith("fixture://"):
            if self._settings.app_mode != "fixture":
                raise ValueError("fixture URLs are disabled in live mode")
            records = self._fixture_resources(pdf_url)
            return ToolResult[list[ResourceRecord]](
                status=Status.OK if records else Status.UNAVAILABLE,
                data=records,
                sources=[SourceRef(title="Bundled resource fixture", url=pdf_url, accessed_at=now)],
                as_of=now,
                warnings=["Fixture mode is enabled; resources are bundled test data."],
            )

        cache_key = hashlib.sha256(f"resources:{pdf_url}".encode()).hexdigest()
        if cached := self._cache.get(cache_key):
            return ToolResult[list[ResourceRecord]].model_validate(cached)

        response = await self._http.get(
            pdf_url,
            allowed_content_types={"application/pdf", "application/octet-stream"},
        )
        if not response.content.startswith(b"%PDF"):
            raise ValueError("downloaded content is not a PDF")
        records = extract_resource_records(response.content, response.url)
        low_confidence = sum(record.confidence < 0.7 for record in records)
        warnings: list[str] = []
        if not records:
            warnings.append("No Indicated or Inferred resource rows could be extracted.")
        if low_confidence:
            warnings.append(f"{low_confidence} row(s) have ambiguous units and require review.")
        result = ToolResult[list[ResourceRecord]](
            status=Status.OK
            if records and not low_confidence
            else (Status.PARTIAL if records else Status.UNAVAILABLE),
            data=records,
            sources=[SourceRef(title="Technical report PDF", url=response.url, accessed_at=now)],
            as_of=now,
            warnings=warnings,
        )
        self._cache.set(
            cache_key,
            result.model_dump(mode="json"),
            self._settings.pdf_cache_ttl_seconds,
        )
        return result
