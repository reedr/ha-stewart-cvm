"""CVM Entity Base class."""

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import CVMCoordinator
from .device import CVMDevice


class CVMEntity(CoordinatorEntity[CVMCoordinator]):
    """Base class."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CVMCoordinator, key: str, name: str) -> None:
        """Set up entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=entry.title,
        )
        self.set_state()

    def set_state(self) -> None:
        """Copy the device data to the entity attributes."""

    @property
    def available(self) -> bool:
        """Return online state."""
        return super().available and self.coordinator.device.online

    @property
    def device(self) -> CVMDevice:
        """Return device."""
        return self.coordinator.device

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.set_state()
        super()._handle_coordinator_update()
