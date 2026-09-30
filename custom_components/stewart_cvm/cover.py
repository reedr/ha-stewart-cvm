"""Screen mask cover."""

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import CVMConfigEntry, CVMCoordinator
from .entity import CVMEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: CVMConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add cover entity."""
    coord = config_entry.runtime_data

    async_add_entities([CVMCover(coord)])


class CVMCover(CVMEntity, CoverEntity):
    """Screen as a cover. Closed is the narrowest preset, fully open the widest."""

    _attr_device_class = CoverDeviceClass.CURTAIN
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, coord: CVMCoordinator) -> None:
        """Get going."""
        super().__init__(coord, "screen_mask", "Screen Mask")

    def set_state(self) -> None:
        """Set how things are."""
        data = self.device.data
        position = data.get("cover_position")
        self._attr_current_cover_position = position
        self._attr_is_closed = None if position is None else position == 0
        self._attr_is_closing = data["motor_status"] == "EXTENDING"
        self._attr_is_opening = data["motor_status"] == "RETRACTING"
        self._attr_extra_state_attributes = dict(data)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set position."""
        await self.device.set_position(int(kwargs[ATTR_POSITION]))

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open up."""
        await self.device.open_mask()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close down."""
        await self.device.close_mask()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop cover."""
        await self.device.stop_mask()
