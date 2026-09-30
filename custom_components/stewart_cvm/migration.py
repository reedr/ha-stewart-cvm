"""Registry migrations: the legacy "CVM" domain and host-based unique IDs."""

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


# Unique ID suffixes used before 0.2.0, when IDs were based on "CVM:<host>".
_LEGACY_KEYS = {"Screen Mask": "screen_mask", "Screen Aspect Ratio": "screen_aspect_ratio"}


def async_migrate_unique_ids(hass: HomeAssistant, entry: CVMConfigEntry) -> None:
    """Rekey host-based device and entity unique IDs to the config entry ID."""
    ent_reg = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        prefix, _, name = entity.unique_id.rpartition("_")
        if prefix.startswith("CVM:") and name in _LEGACY_KEYS:
            ent_reg.async_update_entity(
                entity.entity_id, new_unique_id=f"{entry.entry_id}_{_LEGACY_KEYS[name]}"
            )

    dev_reg = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if any(domain == DOMAIN and ident.startswith("CVM:") for domain, ident in device.identifiers):
            dev_reg.async_update_device(device.id, new_identifiers={(DOMAIN, entry.entry_id)})
