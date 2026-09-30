"""Config, reconfigure and options flows."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stewart_cvm.const import DOMAIN

from .conftest import DATA, OPTIONS


async def _user(hass: HomeAssistant, data: dict):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    return await hass.config_entries.flow.async_configure(result["flow_id"], data)


async def test_user_creates_entry(hass: HomeAssistant, cvm) -> None:
    result = await _user(hass, DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == DATA
    await hass.async_block_till_done()


async def test_user_input_is_trimmed(hass: HomeAssistant, cvm) -> None:
    """Stray spaces around the host, username and preset values are removed."""
    result = await _user(
        hass,
        {
            **DATA,
            "host": " 127.0.0.1 ",
            "username": "user ",
            "cvmpresetar": " 1.78, 2.2, 1.85, 2.4, 2.0, 1.5 ",
            "cvmpresetpos": "5.79 ,1.76,5.06, 0.0,3.52,8.64",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == DATA
    await hass.async_block_till_done()


async def test_user_errors(hass: HomeAssistant, cvm, caplog) -> None:
    result = await _user(hass, {**DATA, "cvmpresetpos": "1,2"})
    assert result["errors"] == {"base": "invalid_presets"}
    result = await _user(hass, {**DATA, "password": "wrong"})
    assert result["errors"] == {"base": "invalid_auth"}
    assert "Setup could not log in: 127.0.0.1 didn't accept the login (timed out)" in caplog.text
    await cvm.stop()
    result = await _user(hass, DATA)
    assert result["errors"] == {"base": "cannot_connect"}
    assert "Setup could not connect: Cannot connect to 127.0.0.1:" in caplog.text
    assert "while opening TCP port" in caplog.text


async def test_user_duplicate_host(hass: HomeAssistant, cvm) -> None:
    MockConfigEntry(domain=DOMAIN, data=DATA, options=OPTIONS).add_to_hass(hass)
    result = await _user(hass, DATA)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure(hass: HomeAssistant, cvm) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={**DATA, "password": "old"}, options=OPTIONS)
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": f" {DATA['host']}", "username": "user", "password": "pass"}
    )
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["password"] == "pass"
    assert entry.data["host"] == DATA["host"]
    await hass.async_block_till_done()


async def test_options_without_recalibrating(hass: HomeAssistant, cvm) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="Stewart CVM", data=DATA, options=OPTIONS)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"cvmpresetar": "1.78,2.4", "cvmpresetpos": "5", "recalibrate": False},
    )
    assert result["errors"] == {"base": "invalid_presets"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"cvmpresetar": "1.78, 2.4", "cvmpresetpos": " 5, 0", "recalibrate": False},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"cvmpresetar": "1.78,2.4", "cvmpresetpos": "5,0"}
    await hass.async_block_till_done()
    # The entry reloads with the new presets.
    select = hass.states.get("select.stewart_cvm_screen_aspect_ratio")
    assert select.attributes["options"] == ["1.78", "2.4"]


async def test_options_recalibrate(hass: HomeAssistant, cvm) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, title="Stewart CVM", data=DATA, options={**OPTIONS, "cvmpresetpos": "0,0,0,0,0,0"}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"cvmpresetar": OPTIONS["cvmpresetar"], "cvmpresetpos": "0,0,0,0,0,0", "recalibrate": True},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["cvmpresetpos"] == "5.79,1.76,5.06,0.0,3.52,8.64"
    await hass.async_block_till_done()
