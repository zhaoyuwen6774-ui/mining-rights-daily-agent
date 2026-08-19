from mining_rights_agent.common.models import Status
from mining_rights_agent.common.settings import Settings
from mining_rights_agent.news.service import NewsService


async def test_fixture_news_search(fixture_settings: Settings) -> None:
    result = await NewsService(fixture_settings).search("Pilbara lithium", 7)

    assert result.status == Status.OK
    assert len(result.data) == 3
    assert result.data[0].relevance_score > 0
    assert all("Fixture" in item.title for item in result.data)
