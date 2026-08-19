from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx


class UnsafeUrlError(ValueError):
    """Raised when a URL could reach a local or otherwise disallowed host."""


class ResponseTooLargeError(ValueError):
    """Raised when a response exceeds the configured byte limit."""


@dataclass(frozen=True)
class FetchResponse:
    url: str
    content: bytes
    content_type: str
    status_code: int


def _is_public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


async def validate_public_https_url(url: str, allowed_hosts: set[str] | None = None) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeUrlError("only unauthenticated public HTTPS URLs are allowed")

    hostname = parsed.hostname.lower().rstrip(".")
    if allowed_hosts is not None and hostname not in allowed_hosts:
        raise UnsafeUrlError(f"host is not allow-listed: {hostname}")

    try:
        literal_address = ipaddress.ip_address(hostname)
    except ValueError:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo, hostname, parsed.port or 443, type=socket.SOCK_STREAM
        )
        if not addresses:
            raise UnsafeUrlError("host did not resolve") from None
        resolved = {str(entry[4][0]) for entry in addresses}
        if not all(_is_public_ip(address) for address in resolved):
            raise UnsafeUrlError("host resolves to a non-public address") from None
    else:
        if not _is_public_ip(str(literal_address)):
            raise UnsafeUrlError("non-public IP addresses are not allowed")


class SafeHttpClient:
    def __init__(self, timeout_seconds: float, max_bytes: int, user_agent: str) -> None:
        self._timeout = timeout_seconds
        self._max_bytes = max_bytes
        self._user_agent = user_agent

    async def get(
        self,
        url: str,
        *,
        allowed_hosts: set[str] | None = None,
        allowed_content_types: set[str] | None = None,
        max_redirects: int = 3,
        headers: dict[str, str] | None = None,
    ) -> FetchResponse:
        current_url = url
        async with httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=False,
            headers={
                "User-Agent": self._user_agent,
                "Accept": (
                    "application/rss+xml, application/xml;q=0.9, "
                    "text/html;q=0.8, */*;q=0.5"
                ),
            },
        ) as client:
            for redirect_count in range(max_redirects + 1):
                await validate_public_https_url(current_url, allowed_hosts)
                async with client.stream("GET", current_url, headers=headers) as response:
                    if response.is_redirect:
                        if redirect_count == max_redirects:
                            raise httpx.TooManyRedirects("redirect limit exceeded")
                        location = response.headers.get("location")
                        if not location:
                            raise httpx.HTTPError("redirect did not include a location")
                        current_url = urljoin(current_url, location)
                        continue

                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if allowed_content_types and content_type not in allowed_content_types:
                        raise ValueError(f"unexpected content type: {content_type or 'missing'}")

                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > self._max_bytes:
                        raise ResponseTooLargeError("response is larger than configured limit")

                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > self._max_bytes:
                            raise ResponseTooLargeError("response is larger than configured limit")
                        chunks.append(chunk)
                    return FetchResponse(
                        url=str(response.url),
                        content=b"".join(chunks),
                        content_type=content_type,
                        status_code=response.status_code,
                    )
        raise httpx.HTTPError("request did not produce a response")
