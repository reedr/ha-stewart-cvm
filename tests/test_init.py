"""Setup, state, commands and unload against the fake controller."""

from __future__ import annotations

import asyncio

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stewart_cvm.const import DOMAIN

from .conftest import DATA, OPTIONS

COVER = "cover.stewart_cvm_screen_mask"
SELECT = "select.stewart_cvm_screen_aspect_ratio"


async def _setup(hass: HomeAssistant, data=DATA, options=OPTIONS) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Stewart CVM", data=data, options=options)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _until(predicate, timeout: float = 3) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.02)


async def test_state_at_startup(hass: HomeAssistant, cvm) -> None:
    """Entities show the reported position right after setup."""
    await _setup(hass)
    cover = hass.states.get(COVER)
    assert cover.state == "open"
    assert cover.attributes["current_position"] == 59
    assert hass.states.get(SELECT).state == "2.0"
    assert hass.states.get(SELECT).attributes["options"] == ["1.5", "1.78", "1.85", "2.0", "2.2", "2.4"]


async def test_select_recalls_preset(hass: HomeAssistant, cvm) -> None:
    """Choosing an aspect ratio recalls its preset and the cover follows."""
    await _setup(hass)
    await hass.services.async_call(
        "select", "select_option", {"entity_id": SELECT, "option": "1.5"}, blocking=True
    )
    await _until(lambda: "#1.1.0.MOTOR=RECALL,6;" in cvm.commands)
    assert hass.states.get(SELECT).state == "1.5"
    await _until(lambda: cvm.status == "STOP" and cvm.position == 8.64)
    coord = hass.config_entries.async_entries(DOMAIN)[0].runtime_data
    await coord.async_refresh()
    await _until(lambda: hass.states.get(COVER).attributes.get("current_position") == 0)
    assert hass.states.get(COVER).state == "closed"


async def test_cover_commands(hass: HomeAssistant, cvm) -> None:
    """Open retracts, close recalls the narrowest preset, stop stops."""
    await _setup(hass)
    for service in ("open_cover", "stop_cover", "close_cover"):
        await hass.services.async_call("cover", service, {"entity_id": COVER}, blocking=True)
    await hass.services.async_call(
        "cover", "set_cover_position", {"entity_id": COVER, "position": 70}, blocking=True
    )
    await _until(lambda: cvm.commands[-1].startswith("#1.1.0.MOTOR=RECALL,2"))
    assert [c for c in cvm.commands if "POSITION" not in c] == [
        "#1.1.0.MOTOR=RETRACT;",
        "#1.1.0.MOTOR=STOP;",
        "#1.1.0.MOTOR=RECALL,6;",
        "#1.1.0.MOTOR=RECALL,2;",
    ]


async def test_unload_closes_connection(hass: HomeAssistant, cvm) -> None:
    """Unload and reload leave exactly one session open."""
    entry = await _setup(hass)
    assert cvm.open_clients == 1
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await _until(lambda: cvm.open_clients == 1)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await _until(lambda: cvm.open_clients == 0)


async def test_connection_lost_and_recovered(hass: HomeAssistant, cvm) -> None:
    """A dropped session makes entities unavailable until the next poll reconnects."""
    entry = await _setup(hass)
    for writer in cvm.clients:
        writer.close()
    await _until(lambda: hass.states.get(COVER).state == STATE_UNAVAILABLE)
    await entry.runtime_data.async_refresh()
    await _until(lambda: hass.states.get(COVER).state == "open")


async def test_not_ready_when_unreachable(hass: HomeAssistant, cvm) -> None:
    """An unreachable controller retries setup without a traceback."""
    await cvm.stop()
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_invalid_presets_fail_setup(hass: HomeAssistant, cvm) -> None:
    """Mismatched preset lists are a setup error, not a crash."""
    entry = await _setup(hass, options={**OPTIONS, "cvmpresetpos": "1,2"})
    assert entry.state is ConfigEntryState.SETUP_ERROR
