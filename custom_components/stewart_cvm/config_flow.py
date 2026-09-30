"""Config flow for the Stewart CVM integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_LEGACY_ENTRY,
    CONF_RECALIBRATE,
    CVM_PRESETS_ASPECT,
    CVM_PRESETS_POSITION,
    DOMAIN,
    LEGACY_DOMAIN,
)
from .device import CVMAuthError, CVMConnectionError, CVMDevice, parse_aspects, parse_presets

_LOGGER = logging.getLogger(__name__)

CONNECTION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

CONFIG_USER_DATA_SCHEMA = CONNECTION_SCHEMA.extend(
    {
        vol.Required(CVM_PRESETS_ASPECT): str,
        vol.Required(CVM_PRESETS_POSITION): str
    }
)

OPTIONS_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CVM_PRESETS_ASPECT): str,
        vol.Required(CVM_PRESETS_POSITION): str,
        vol.Required(CONF_RECALIBRATE, default=True): bool,
    }
)


async def validate_connection(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Try to log in; return form errors."""
    dev = CVMDevice(
        hass, data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD], "1", "0"
    )
    try:
        await dev.test_connection()
    except CVMAuthError:
        return {"base": "invalid_auth"}
    except CVMConnectionError:
        return {"base": "cannot_connect"}
    except Exception:
        _LOGGER.exception("Unexpected exception")
        return {"base": "unknown"}
    return {}


class ConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Stewart CVM."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._skip_legacy = False

    def _legacy_entries(self) -> list[ConfigEntry]:
        """Config entries of the legacy "CVM" package not yet imported."""
        imported = {
            entry.data.get(CONF_LEGACY_ENTRY)
            for entry in self.hass.config_entries.async_entries(DOMAIN)
        }
        return [
            entry
            for entry in self.hass.config_entries.async_entries(LEGACY_DOMAIN)
            if entry.entry_id not in imported
        ]

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is None and not self._skip_legacy and self._legacy_entries():
            return self.async_show_menu(
                step_id="user", menu_options=["import_legacy", "manual"]
            )

        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})
            try:
                parse_presets(user_input[CVM_PRESETS_ASPECT], user_input[CVM_PRESETS_POSITION])
            except ValueError:
                errors["base"] = "invalid_presets"
            else:
                errors = await validate_connection(self.hass, user_input)
            if not errors:
                return self.async_create_entry(title="Stewart CVM", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(CONFIG_USER_DATA_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up a new controller instead of importing the legacy one."""
        self._skip_legacy = True
        return await self.async_step_user()

    async def async_step_import_legacy(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Import the legacy entry: same settings, device and entity IDs."""
        legacies = self._legacy_entries()
        if not legacies:
            return self.async_abort(reason="no_legacy_entry")
        legacy = legacies[0]
        self._async_abort_entries_match({CONF_HOST: legacy.data[CONF_HOST]})
        if user_input is None:
            return self.async_show_form(
                step_id="import_legacy",
                description_placeholders={
                    "title": legacy.title,
                    "host": legacy.data[CONF_HOST],
                },
            )
        return self.async_create_entry(
            title=legacy.title,
            data={**legacy.data, CONF_LEGACY_ENTRY: legacy.entry_id},
            options=dict(legacy.options),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the host or login."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if any(
                other.data[CONF_HOST] == user_input[CONF_HOST]
                for other in self._async_current_entries(include_ignore=False)
                if other.entry_id != entry.entry_id
            ):
                return self.async_abort(reason="already_configured")
            errors = await validate_connection(self.hass, user_input)
            if not errors:
                return self.async_update_reload_and_abort(entry, data_updates=user_input)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                CONNECTION_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )


class OptionsFlowHandler(OptionsFlow):
    """Handle an options flow for Stewart CVM."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit the presets, optionally recalibrating the motor positions."""
        errors: dict[str, str] = {}
        if user_input is not None:
            aspects = user_input[CVM_PRESETS_ASPECT]
            positions = user_input[CVM_PRESETS_POSITION]
            try:
                if user_input[CONF_RECALIBRATE]:
                    parse_aspects(aspects)
                else:
                    parse_presets(aspects, positions)
            except ValueError:
                errors["base"] = "invalid_presets"

            if not errors and user_input[CONF_RECALIBRATE]:
                try:
                    positions = await self.config_entry.runtime_data.device.async_recalibrate(aspects)
                except CVMConnectionError:
                    errors["base"] = "cannot_connect"
                except TimeoutError:
                    errors["base"] = "recalibrate_failed"
                except Exception:
                    _LOGGER.exception("Recalibration error")
                    errors["base"] = "recalibrate_exception"
                else:
                    _LOGGER.info("Recalibrated motor positions: presets=%s positions=%s", aspects, positions)

            if not errors:
                return self.async_create_entry(
                    data={CVM_PRESETS_ASPECT: aspects, CVM_PRESETS_POSITION: positions}
                )

        previous_data = user_input or {
            CVM_PRESETS_ASPECT: self.config_entry.options.get(CVM_PRESETS_ASPECT, self.config_entry.data[CVM_PRESETS_ASPECT]),
            CVM_PRESETS_POSITION: self.config_entry.options.get(CVM_PRESETS_POSITION, self.config_entry.data[CVM_PRESETS_POSITION])
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(OPTIONS_USER_DATA_SCHEMA, previous_data),
            errors=errors
        )
