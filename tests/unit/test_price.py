from mining_rights_agent.common.models import Status
from mining_rights_agent.common.settings import Settings
from mining_rights_agent.price.service import LmePriceService


async def test_fixture_copper_trend(fixture_settings: Settings) -> None:
    result = await LmePriceService(fixture_settings).get_trend("copper", 7)

    assert result.status == Status.OK
    assert result.data is not None
    assert result.data.change_percent is not None
    assert len(result.data.points) == 5


async def test_lithium_is_not_relabelled_as_lme(fixture_settings: Settings) -> None:
    result = await LmePriceService(fixture_settings).get_trend("lithium", 7)

    assert result.status == Status.UNAVAILABLE
    assert result.data is None
    assert "no proxy price" in result.warnings[0]
