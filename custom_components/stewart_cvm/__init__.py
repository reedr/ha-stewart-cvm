"""The Stewart CVM integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError

from .const import CVM_PRESETS_ASPECT, CVM_PRESETS_POSITION
from .coordinator import CVMConfigEntry, CVMCoordinator
from .device import CVMDevice
from .migration import async_migrate_legacy_entry, async_migrate_unique_ids

_PLATFORMS: list[Platform] = [Platform.COVER, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: CVMConfigEntry) -> bool:
    """Set up CVM device from a config entry."""

    async_migrate_legacy_entry(hass, entry)
    async_migrate_unique_ids(hass, entry)

    try:
        dev = CVMDevice(
            hass,
            entry.data[CONF_HOST],
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            entry.options.get(CVM_PRESETS_ASPECT, entry.data[CVM_PRESETS_ASPECT]),
            entry.options.get(CVM_PRESETS_POSITION, entry.data[CVM_PRESETS_POSITION]),
        )
    except ValueError as err:
        raise ConfigEntryError(f"Invalid presets: {err}") from err
    coord = CVMCoordinator(hass, entry, dev)
    entry.runtime_data = coord
    entry.async_on_unload(dev.async_close)
    await coord.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True

async def async_update_options(hass: HomeAssistant, entry: CVMConfigEntry) -> None:
    """Reload with the new presets."""
    hass.config_entries.async_schedule_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: CVMConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
