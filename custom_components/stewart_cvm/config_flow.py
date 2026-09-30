"""Config flow for the Stewart CVM integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_LEGACY_ENTRY,
    CVM_PRESETS_ASPECT,
    CVM_PRESETS_POSITION,
    DOMAIN,
    LEGACY_DOMAIN,
)
from .device import CVMDevice

_LOGGER = logging.getLogger(__name__)

CONFIG_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CVM_PRESETS_ASPECT): str,
        vol.Required(CVM_PRESETS_POSITION): str
    }
)

OPTIONS_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CVM_PRESETS_ASPECT): str,
        vol.Required(CVM_PRESETS_POSITION): str
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""

    dev = CVMDevice(hass, data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD], data[CVM_PRESETS_ASPECT], data[CVM_PRESETS_POSITION])
    if await dev.test_connection():
        return {"title": "Stewart CVM"}

    raise CannotConnect

class ConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for 2N Intercom."""

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
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=CONFIG_USER_DATA_SCHEMA, errors=errors
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

class OptionsFlowHandler(OptionsFlow):
    """Handle a options flow for 2N Intercom."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                coord = self.config_entry.runtime_data
                dev = coord.device
                motor_positions = await dev.async_recalibrate(user_input[CVM_PRESETS_ASPECT])
            except Exception as err:
                _LOGGER.exception("Recalibrate exception: %s", err)
                errors["base"] = "recalibrate_exception"
            else:
                if motor_positions is not None:
                    user_input[CVM_PRESETS_POSITION] = motor_positions
                    _LOGGER.info("Recalibrated motor positions: presets=%s positions=%s", user_input[CVM_PRESETS_ASPECT], motor_positions)
                    return self.async_create_entry(data=user_input)
                else:
                    errors["base"] = "recalibrate_failed"

        previous_data = {
            CVM_PRESETS_ASPECT: self.config_entry.options.get(CVM_PRESETS_ASPECT, self.config_entry.data[CVM_PRESETS_ASPECT]),
            CVM_PRESETS_POSITION: self.config_entry.options.get(CVM_PRESETS_POSITION, self.config_entry.data[CVM_PRESETS_POSITION])
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(OPTIONS_USER_DATA_SCHEMA, previous_data),
            errors=errors
        )

@staticmethod
@callback
def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
    """Create the options flow."""
    return OptionsFlowHandler()

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
