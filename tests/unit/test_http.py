import pytest

from mining_rights_agent.common.http import UnsafeUrlError, validate_public_https_url


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/report.pdf",
        "https://127.0.0.1/report.pdf",
        "https://169.254.169.254/latest/meta-data",
        "https://user:secret@example.com/report.pdf",
    ],
)
async def test_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        await validate_public_https_url(url)
