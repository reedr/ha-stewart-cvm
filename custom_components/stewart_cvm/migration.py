"""Take over the device and entities of a config entry from the legacy "CVM" domain."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import CONF_LEGACY_ENTRY, DOMAIN, LEGACY_DOMAIN
from .coordinator import CVMConfigEntry

_LOGGER = logging.getLogger(__name__)


def async_migrate_legacy_entry(hass: HomeAssistant, entry: CVMConfigEntry) -> None:
    """Move the legacy entry's device and entities onto this entry, then remove it.

    Device and entity registry IDs are kept, so entity IDs, history, areas, labels,
    customizations and device-based automations carry over unchanged.
    """
    legacy_id = entry.data.get(CONF_LEGACY_ENTRY)
    if legacy_id is None:
        return

    legacy = hass.config_entries.async_get_entry(legacy_id)
    if legacy is not None and legacy.domain == LEGACY_DOMAIN:
        dev_reg = dr.async_get(hass)
        ent_reg = er.async_get(hass)

        for entity in er.async_entries_for_config_entry(ent_reg, legacy_id):
            ent_reg.async_update_entity_platform(
                entity.entity_id, DOMAIN, new_config_entry_id=entry.entry_id
            )
            _LOGGER.info("Took over %s from the legacy CVM integration", entity.entity_id)

        for device in dr.async_entries_for_config_entry(dev_reg, legacy_id):
            dev_reg.async_update_device(
                device.id,
                new_config_entry_id=entry.entry_id,
                new_identifiers={
                    (DOMAIN, ident) if domain == LEGACY_DOMAIN else (domain, ident)
                    for domain, ident in device.identifiers
                },
            )

        hass.async_create_task(hass.config_entries.async_remove(legacy_id))

    data = {k: v for k, v in entry.data.items() if k != CONF_LEGACY_ENTRY}
    hass.config_entries.async_update_entry(entry, data=data)
