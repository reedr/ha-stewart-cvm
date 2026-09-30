"""Screen aspect ratio select."""

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import CVMConfigEntry, CVMCoordinator
from .entity import CVMEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: CVMConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add select entity."""
    coord = config_entry.runtime_data

    async_add_entities([CVMSelect(coord)])


class CVMSelect(CVMEntity, SelectEntity):
    """Screen aspect selector."""

    def __init__(self, coord: CVMCoordinator) -> None:
        """Get going."""
        self._pending_option: str | None = None
        super().__init__(coord, "screen_aspect_ratio", "Screen Aspect Ratio")

    def set_state(self) -> None:
        """Set how things are."""
        data = self.device.data
        self._attr_options = [ar["name"] for ar in data["aspect_ratios"]]
        if self._pending_option is not None and data["motor_status"] != "STOP":
            # Show the chosen preset while the mask travels past the others.
            self._attr_current_option = self._pending_option
        else:
            self._pending_option = None
            self._attr_current_option = data["screen_aspect_ratio_string"]

    async def async_select_option(self, option: str) -> None:
        """Recall the preset; show it until the device reports otherwise."""
        await self.device.set_aspect_ratio(option)
        self._pending_option = option
        self._attr_current_option = option
        self.async_write_ha_state()
