"""Device parsing and calibration."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from custom_components.stewart_cvm.device import CVMDevice, parse_presets

from .conftest import ASPECTS, HOST, POSITIONS
from .fake_cvm import PRESET_POSITIONS


def test_parse_presets() -> None:
    presets = parse_presets(ASPECTS, POSITIONS)
    assert [ar["name"] for ar in presets] == ["1.5", "1.78", "1.85", "2.0", "2.2", "2.4"]
    assert [ar["cover_position"] for ar in presets] == [0, 32, 41, 59, 79, 100]
    assert parse_presets("2.0", "0")[0]["cover_position"] == 100


@pytest.mark.parametrize(
    ("aspects", "positions"),
    [("1.78,x", "1,2"), ("1.78,2.4", "1"), ("1.78,1.78", "1,2"), ("1.78", "")],
)
def test_parse_presets_invalid(aspects: str, positions: str) -> None:
    with pytest.raises(ValueError):
        parse_presets(aspects, positions)


@pytest.mark.parametrize("start", [3.52, 8.64])
async def test_recalibrate(hass: HomeAssistant, cvm, start: float) -> None:
    """Calibration waits for real motion, even when position reports lag the recall.

    Starting at 8.64, the first preset (1.5) needs no motion at all.
    """
    cvm.position = start
    cvm.start_delay = 0.2
    dev = CVMDevice(hass, HOST, "user", "pass", ASPECTS, "0,0,0,0,0,0")
    await dev.async_init(lambda data: None)
    try:
        result = await dev.async_recalibrate(ASPECTS)
    finally:
        await dev.async_close()
    assert [float(p) for p in result.split(",")] == PRESET_POSITIONS


async def test_enode_config_lines_not_warned(hass: HomeAssistant, cvm, caplog) -> None:
    """The e-Node's CS-Bus config echo (!UID...) is ignored quietly; other junk still warns."""
    dev = CVMDevice(hass, HOST, "user", "pass", ASPECTS, POSITIONS)
    await dev.async_init(lambda data: None)
    try:
        caplog.clear()
        cvm._broadcast("!UID2.C.BUS.SHADOW.1=255.255.255;")
        cvm._broadcast("!UID2.C.BUS.ACTION.8=0;")
        cvm._broadcast("garbage")
        await dev.async_read_position()
    finally:
        await dev.async_close()
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert not any("UID2" in m for m in warnings)
    assert any("garbage" in m for m in warnings)
