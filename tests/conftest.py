"""Fixtures for Stewart CVM tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from .fake_cvm import FakeCVM

pytest_plugins = ("pytest_homeassistant_custom_component",)

HOST = "127.0.0.1"
ASPECTS = "1.78,2.2,1.85,2.4,2.0,1.5"
POSITIONS = "5.79,1.76,5.06,0.0,3.52,8.64"
DATA = {
    "host": HOST,
    "username": "user",
    "password": "pass",
    "cvmpresetar": ASPECTS,
    "cvmpresetpos": POSITIONS,
}
OPTIONS = {"cvmpresetar": ASPECTS, "cvmpresetpos": POSITIONS}


@pytest.fixture(autouse=True)
def enable_cvm_integration(enable_custom_integrations):
    """Allow Home Assistant to load the custom integration under test."""


@pytest.fixture(autouse=True)
def fast_timing():
    """Shrink the device's timeouts and intervals."""
    module = "custom_components.stewart_cvm.device"
    with (
        patch(f"{module}.CVM_LOGIN_TIMEOUT", 0.5),
        patch(f"{module}.CVM_MIN_COMMAND_INTERVAL", 0.02),
        patch(f"{module}.CVM_MOTION_TIMEOUT", 0.5),
        patch(f"{module}.CVM_CALIBRATE_TIMEOUT", 3),
        patch(f"{module}.CVM_SETTLE_TIME", 0.05),
    ):
        yield


@pytest.fixture
async def cvm(socket_enabled):
    """A fake controller; the integration connects to it on 127.0.0.1."""
    server = FakeCVM()
    await server.start()
    with patch("custom_components.stewart_cvm.device.CVM_PORT", server.port):
        yield server
    await server.stop()
