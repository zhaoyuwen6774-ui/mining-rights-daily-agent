from __future__ import annotations

import re

import httpx

from mining_rights_agent.common.settings import Settings

CITATION_PATTERN = re.compile(r"\[(?:N|R|P)\d+\]")


class OptionalLlmPolisher:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def enabled(self) -> bool:
        return bool(
            self._settings.llm_base_url and self._settings.llm_api_key and self._settings.llm_model
        )

    async def conclusion(self, evidence: str, allowed_citations: set[str]) -> str | None:
        base_url = self._settings.llm_base_url
        api_key = self._settings.llm_api_key
        model = self._settings.llm_model
        if not base_url or not api_key or not model:
            return None
        url = f"{base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Write one concise Chinese mining brief conclusion using only the supplied "
                        "evidence. Preserve citation markers such as [N1]. Do not introduce facts, "
                        "numbers, URLs, or unsupported causal claims."
                    ),
                },
                {"role": "user", "content": evidence},
            ],
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=self._settings.http_timeout_seconds) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
        content = str(response.json()["choices"][0]["message"]["content"]).strip()
        used = set(CITATION_PATTERN.findall(content))
        if not content or not used or not used.issubset(allowed_citations):
            return None
        return content
