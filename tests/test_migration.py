"""Import of the legacy "CVM" package's config entry."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stewart_cvm.const import CONF_LEGACY_ENTRY, DOMAIN, LEGACY_DOMAIN

from .conftest import HOST, LEGACY_DATA, LEGACY_OPTIONS

DEVICE_ID = f"CVM:{HOST}"
COVER = "cover.cvm_10_0_1_143_screen_mask"
SELECT = "select.cvm_10_0_1_143_screen_aspect_ratio"


def _legacy_setup(hass: HomeAssistant) -> tuple[MockConfigEntry, str]:
    """Registry contents left behind by the old package, with user customizations."""
    legacy = MockConfigEntry(
        domain=LEGACY_DOMAIN, title="Stewart CVM", data=LEGACY_DATA, options=LEGACY_OPTIONS
    )
    legacy.add_to_hass(hass)
    area = ar.async_get(hass).async_create("Theater")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=legacy.entry_id,
        identifiers={(LEGACY_DOMAIN, DEVICE_ID)},
        manufacturer="Stewart",
        model="CVM",
        name=DEVICE_ID,
    )
    dr.async_get(hass).async_update_device(device.id, area_id=area.id, name_by_user="Screen")
    ent_reg = er.async_get(hass)
    for platform, name, entity_id in (
        ("cover", "Screen Mask", COVER),
        ("select", "Screen Aspect Ratio", SELECT),
    ):
        ent_reg.async_get_or_create(
            platform,
            LEGACY_DOMAIN,
            f"{DEVICE_ID}_{name}",
            config_entry=legacy,
            device_id=device.id,
            suggested_object_id=entity_id.split(".", 1)[1],
        )
    ent_reg.async_update_entity(COVER, name="Mask", labels={"theater"})
    return legacy, device.id


async def test_flow_offers_import(hass: HomeAssistant, mock_cvm) -> None:
    """With a legacy entry present, the flow offers to import it."""
    legacy, _ = _legacy_setup(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["import_legacy", "manual"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "import_legacy"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"]["host"] == HOST

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == LEGACY_OPTIONS
    await hass.async_block_till_done()

    entry = result["result"]
    assert CONF_LEGACY_ENTRY not in entry.data
    assert entry.data == LEGACY_DATA
    assert hass.config_entries.async_get_entry(legacy.entry_id) is None


async def test_manual_path(hass: HomeAssistant, mock_cvm) -> None:
    """Choosing manual setup shows the normal form."""
    _legacy_setup(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_no_legacy_shows_form(hass: HomeAssistant, mock_cvm) -> None:
    """Without a legacy entry, setup goes straight to the form."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_takeover_keeps_ids(hass: HomeAssistant, mock_cvm) -> None:
    """Device and entities keep their IDs and customizations."""
    legacy, device_id = _legacy_setup(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Stewart CVM",
        data={**LEGACY_DATA, CONF_LEGACY_ENTRY: legacy.entry_id},
        options=LEGACY_OPTIONS,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    ent_reg = er.async_get(hass)
    for entity_id in (COVER, SELECT):
        reg = ent_reg.async_get(entity_id)
        assert reg.platform == DOMAIN
        assert reg.config_entry_id == entry.entry_id
        assert reg.device_id == device_id
    assert ent_reg.async_get(COVER).name == "Mask"
    assert ent_reg.async_get(COVER).labels == {"theater"}
    assert len(er.async_entries_for_config_entry(ent_reg, entry.entry_id)) == 2

    device = dr.async_get(hass).async_get(device_id)
    assert device.identifiers == {(DOMAIN, DEVICE_ID)}
    assert device.config_entries == {entry.entry_id}
    assert device.name_by_user == "Screen"
    assert device.area_id == "theater"

    coord = entry.runtime_data
    coord.async_set_updated_data(coord.device.data)
    await hass.async_block_till_done()
    assert hass.states.get(COVER).attributes["current_position"] == 59
    assert hass.states.get(SELECT).state == "2.0"
    assert hass.config_entries.async_get_entry(legacy.entry_id) is None
    assert CONF_LEGACY_ENTRY not in entry.data
