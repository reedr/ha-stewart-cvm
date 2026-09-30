"""Fixtures for Stewart CVM tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.stewart_cvm.device import CVMDevice

pytest_plugins = ("pytest_homeassistant_custom_component",)

HOST = "10.0.1.143"
LEGACY_DATA = {
    "host": HOST,
    "username": "user",
    "password": "pass",
    "cvmpresetar": "1.78,2.2,1.85,2.4,2.0,1.5",
    "cvmpresetpos": "5.79,1.76,5.06,0.0,3.52,8.64",
}
LEGACY_OPTIONS = {
    "cvmpresetar": "1.78,2.2,1.85,2.4,2.0,1.5",
    "cvmpresetpos": "5.79,1.76,5.06,0.0,3.52,8.64",
}


@pytest.fixture(autouse=True)
def enable_cvm_integration(enable_custom_integrations):
    """Allow Home Assistant to load the custom integration under test."""


@pytest.fixture
def mock_cvm():
    """Replace the telnet session: the mask reports the 2.0 preset."""

    async def fake_init(self, data_callback):
        self._callback = data_callback
        self._online = True
        ar = self.aspect_ratio_lookup("2.0")
        self._data.update(
            cover_position=ar["cover_position"],
            motor_position=ar["motor_position"],
            screen_aspect_ratio=ar["value"],
            screen_aspect_ratio_string=ar["name"],
            screen_preset=ar["preset"],
        )
        return self._data

    with (
        patch.object(CVMDevice, "async_init", fake_init),
        patch.object(CVMDevice, "send_query_position", AsyncMock(return_value=True)),
        patch.object(CVMDevice, "test_connection", AsyncMock(return_value=True)),
    ):
        yield
