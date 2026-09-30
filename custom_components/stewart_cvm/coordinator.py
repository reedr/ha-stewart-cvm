"""Stewart CVM coordinator."""

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .device import CVMConnectionError, CVMDevice

_LOGGER = logging.getLogger(__name__)

type CVMConfigEntry = ConfigEntry[CVMCoordinator]

class CVMCoordinator(DataUpdateCoordinator[dict]):
    """Polls the mask position; the device pushes changes as they arrive."""

    def __init__(
        self, hass: HomeAssistant, config_entry: CVMConfigEntry, device: CVMDevice
    ) -> None:
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="CVM Coordinator",
            config_entry=config_entry,
            update_interval=timedelta(seconds=5),
            # Polls return the same dict the device updates in place, so only pushes
            # and availability changes notify entities.
            setup_method = self.async_init,
            update_method = self.async_update,
            always_update=False,
        )
        self._device = device

    @property
    def device(self) -> CVMDevice:
        """The device handle."""
        return self._device

    async def async_init(self) -> None:
        """Connect and wait for the first position report."""
        try:
            await self.device.async_init(self.update_callback)
        except CVMConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except TimeoutError as err:
            raise UpdateFailed(f"No position report from {self.device.host}") from err

    async def async_update(self) -> dict:
        """Query the position; the answer arrives through the listener."""
        try:
            await self.device.send_query_position()
        except CVMConnectionError as err:
            raise UpdateFailed(str(err)) from err
        return self.device.data

    @callback
    def update_callback(self, data: dict) -> None:
        """Incoming data callback."""
        self.async_set_updated_data(data)
