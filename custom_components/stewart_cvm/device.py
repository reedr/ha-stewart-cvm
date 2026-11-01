"""Stewart CVM Device."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
import logging
from operator import itemgetter
import re
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CVM_CALIBRATE_TIMEOUT,
    CVM_CONNECT_TIMEOUT,
    CVM_LOGIN_TIMEOUT,
    CVM_MIN_COMMAND_INTERVAL,
    CVM_MOTION_TIMEOUT,
    CVM_PORT,
    CVM_SETTLE_TIME,
)

_LOGGER = logging.getLogger(__name__)

MIN_COVER_POSITION = 0 # narrowest
MAX_COVER_POSITION = 100 # widest


class CVMConnectionError(HomeAssistantError):
    """Error to indicate the controller can't be reached."""


class CVMAuthError(CVMConnectionError):
    """Error to indicate the controller didn't accept the login."""


def parse_aspects(presets_aspect: str) -> list[dict[str, Any]]:
    """Parse the preset aspect ratios, in preset order, sorted by value."""
    names = [ar.strip() for ar in presets_aspect.split(",")]
    try:
        values = [float(ar) for ar in names]
    except ValueError as err:
        raise ValueError("Aspect ratios must be comma-separated numbers") from err
    if len(set(values)) != len(values):
        raise ValueError("Aspect ratios must be unique")
    return sorted(
        [{"name": name, "value": value, "preset": i + 1}
         for i, (name, value) in enumerate(zip(names, values, strict=True))],
        key=itemgetter("value"),
    )


def parse_presets(presets_aspect: str, presets_position: str) -> list[dict[str, Any]]:
    """Parse the preset aspect ratios and motor positions, sorted by aspect ratio."""
    aspect_ratios = parse_aspects(presets_aspect)
    try:
        motor_positions = [float(p) for p in presets_position.split(",")]
    except ValueError as err:
        raise ValueError("Motor positions must be comma-separated numbers") from err
    if len(motor_positions) != len(aspect_ratios):
        raise ValueError("There must be one motor position per aspect ratio")
    max_position = max(motor_positions)
    for ar in aspect_ratios:
        ar["motor_position"] = motor_positions[ar["preset"] - 1]
        ar["cover_position"] = (
            int((max_position - ar["motor_position"]) * MAX_COVER_POSITION / max_position)
            if max_position > 0
            else MAX_COVER_POSITION
        )
    return aspect_ratios


class CVMDevice:
    """Represents a single CVM device."""

    def __init__(
        self, hass: HomeAssistant, host: str, username: str, password: str, presets_aspect: str, presets_position: str
    ) -> None:
        """Set up class. Raises ValueError for invalid presets."""

        self._hass = hass
        self._host = host
        self._username = username
        self._password = password
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._online = False
        self._callback: Callable[[dict], None] | None = None
        pat = r'[^!#]*([!#])1\.1\.(\d)\.MOTOR(\.[^=]+)?=([?.0-9A-Z]+)'
        self._match_re = re.compile(pat.encode('ascii'))
        self._aspect_ratios = []
        self._data = {
                        "position": None,
                        "motor_status": "STOP",
                        "motor_position": None,
                        "screen_aspect_ratio": None,
                        "screen_aspect_ratio_string": None,
                        "screen_preset": None
                      }
        self.set_aspect_ratios(presets_aspect, presets_position)
        self._init_event = asyncio.Event()
        self._motion_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._position_event = asyncio.Event()
        self._connect_lock = asyncio.Lock()
        self._last_command_sent = None
        self._is_moving = False
        self._listener: asyncio.Task | None = None

    def set_aspect_ratios(self, presets_aspect: str, presets_positions: str) -> None:
        """Set aspect ratios and motor positions."""
        self._aspect_ratios = parse_presets(presets_aspect, presets_positions)
        for ar in self._aspect_ratios:
            _LOGGER.info("aspect ratio: '%s' => %.2f cover=%d motor=%.2f preset=%d", ar["name"], ar["value"], ar["cover_position"], ar["motor_position"], ar["preset"])
        self._data["aspect_ratios"] = self._aspect_ratios

    @property
    def host(self) -> str:
        """Controller host."""
        return self._host

    @property
    def online(self) -> bool:
        """Return status."""
        return self._online

    @property
    def data(self) -> dict:
        """Dev data."""
        return self._data

    @property
    def aspect_ratios(self) -> list[str]:
        """Strings for aspect ratios."""
        return [ar["name"] for ar in self._aspect_ratios]

    def cover_position_to_aspect(self, position: int) -> dict:
        """Find aspect just larger than position."""
        if position <= MIN_COVER_POSITION:
            return self._aspect_ratios[0]
        if position >= MAX_COVER_POSITION:
            return self._aspect_ratios[-1]
        for ar in self._aspect_ratios:
            if position <= ar["cover_position"]:
                return ar
        return self._aspect_ratios[-1]

    def motor_position_to_aspect(self, position: float) -> dict:
        """Find the aspect whose motor position is closest."""
        return min(self._aspect_ratios, key=lambda ar: abs(position - ar["motor_position"]))

    def aspect_ratio_lookup(self, aspect: str) -> dict | None:
        """Lookup the aspect."""
        for ar in self._aspect_ratios:
            if ar["name"] == aspect:
                return ar
        return None

    async def open_connection(self, test: bool=False) -> bool:
        """Establish a connection. Raises CVMConnectionError or CVMAuthError."""
        async with self._connect_lock:
            if self._online and self._writer is not None and not self._writer.is_closing():
                return True

            writer = None
            stage = f"opening TCP port {CVM_PORT}"
            try:
                _LOGGER.debug("Connecting to %s:%d", self._host, CVM_PORT)
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, CVM_PORT),
                    timeout=CVM_CONNECT_TIMEOUT
                )
                stage = "waiting for the User: prompt"
                _LOGGER.debug("%s: %s", self._host, stage)
                await asyncio.wait_for(
                    reader.readuntil(b"User:"),
                    timeout=CVM_LOGIN_TIMEOUT
                )
                writer.write(self._username.encode('ascii') + b"\r")
                stage = "waiting for the Password: prompt"
                _LOGGER.debug("%s: %s", self._host, stage)
                await asyncio.wait_for(
                    reader.readuntil(b"Password:"),
                    timeout=CVM_LOGIN_TIMEOUT
                )
                writer.write(self._password.encode('ascii') + b"\r")
                stage = "logging in"
                _LOGGER.debug("%s: waiting for Connected: after the password", self._host)
                await asyncio.wait_for(
                    reader.readuntil(b"Connected:"),
                    timeout=CVM_LOGIN_TIMEOUT
                )
            except (TimeoutError, OSError, asyncio.IncompleteReadError, asyncio.LimitOverrunError) as err:
                self._online = False
                if writer is not None:
                    await self._close_writer(writer)
                if isinstance(err, TimeoutError):
                    reason = "timed out"
                elif isinstance(err, asyncio.IncompleteReadError):
                    reason = f"connection closed by the controller after {err.partial!r}"
                else:
                    reason = repr(err)
                _LOGGER.debug("%s: failed while %s: %s", self._host, stage, reason)
                if stage == "logging in":
                    raise CVMAuthError(
                        f"{self._host} didn't accept the login ({reason}); check the username and password"
                    ) from err
                raise CVMConnectionError(
                    f"Cannot connect to {self._host}: {reason} while {stage}"
                ) from err

            _LOGGER.debug("%s: logged in", self._host)
            if test:
                await self._close_writer(writer)
            else:
                self._reader, self._writer = reader, writer
                self._online = True
                self._listener = self._hass.async_create_background_task(
                    self.listener(), f"stewart_cvm listener {self._host}"
                )
                self._notify()  # entities become available again
            return True

    @staticmethod
    async def _close_writer(writer: asyncio.StreamWriter) -> None:
        """Close a connection, ignoring errors."""
        writer.close()
        with suppress(OSError):
            await writer.wait_closed()

    async def test_connection(self) -> bool:
        """Test a connect."""
        return await self.open_connection(test=True)

    async def async_close(self) -> None:
        """Stop listening and close the connection."""
        self._callback = None
        self._online = False
        if self._listener is not None:
            self._listener.cancel()
            with suppress(asyncio.CancelledError):
                await self._listener
            self._listener = None
        if self._writer is not None:
            await self._close_writer(self._writer)
            self._writer = None

    async def maybe_delay_command(self, wait: bool = True) -> bool:
        """Wait if it's been too soon."""
        if self._last_command_sent is not None:
            dt = time.time() - self._last_command_sent
            if dt < CVM_MIN_COMMAND_INTERVAL:
                if wait:
                    await asyncio.sleep(CVM_MIN_COMMAND_INTERVAL - dt)
                else:
                    return False
        return True

    async def send_command(self, command: str) -> bool:
        """Make an API call. Raises CVMConnectionError."""
        await self.open_connection()
        cmd = command.encode('ascii') + b"\r\n"
        _LOGGER.debug("-> %s", str(cmd))
        try:
            self._writer.write(cmd)
            await self._writer.drain()
        except OSError as err:
            self._online = False
            raise CVMConnectionError(f"Lost connection to {self._host}: {err!r}") from err
        self._last_command_sent = time.time()
        return True

    async def send_query_position(self) -> bool:
        """Query."""
        if await self.maybe_delay_command(wait=False):
            return await self.send_command("#1.1.1.MOTOR.POSITION=?")
        return False

    async def send_recall(self, preset: int) -> bool:
        """Recall a preset."""
        await self.maybe_delay_command()
        return await self.send_command(f"#1.1.0.MOTOR=RECALL,{preset};")

    async def set_aspect_ratio(self, aspect: str) -> bool:
        """Set mask from aspect ratio."""
        ar = self.aspect_ratio_lookup(aspect)
        if ar is None:
            raise ValueError(f"Unknown aspect ratio {aspect}")
        _LOGGER.debug("set_aspect_ratio: %s => %.2f cover=%d motor=%.2f preset=%d", aspect, ar["value"], ar["cover_position"], ar["motor_position"], ar["preset"])
        return await self.send_recall(ar["preset"])

    async def set_position(self, position: int) -> bool:
        """Setit."""
        ar = self.cover_position_to_aspect(position)
        return await self.send_recall(ar["preset"])

    async def open_mask(self) -> bool:
        """Open wide."""
        return await self.send_command("#1.1.0.MOTOR=RETRACT;")

    async def close_mask(self) -> bool:
        """Narrow bridge."""
        return await self.set_position(0)

    async def stop_mask(self) -> bool:
        """Stop moving."""
        return await self.send_command("#1.1.0.MOTOR=STOP;")

    async def _wait_polling(self, event: asyncio.Event, timeout: float) -> bool:
        """Wait for an event, querying the position meanwhile. False on timeout."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not event.is_set():
            remaining = deadline - loop.time()
            if remaining <= 0:
                return False
            await self.send_query_position()
            with suppress(TimeoutError):
                await asyncio.wait_for(event.wait(), min(remaining, CVM_MIN_COMMAND_INTERVAL))
        return True

    async def async_read_position(self) -> float:
        """Query the motor position and wait for the answer."""
        self._position_event.clear()
        await self.maybe_delay_command()
        await self.send_command("#1.1.1.MOTOR.POSITION=?")
        await asyncio.wait_for(self._position_event.wait(), timeout=CVM_LOGIN_TIMEOUT)
        return self._data["motor_position"]

    async def async_recalibrate(self, presets_aspect: str) -> str:
        """Recall each preset and record where the motor stops.

        Returns the motor positions in preset order. Raises ValueError for invalid
        aspect ratios, TimeoutError if the motor doesn't stop, or CVMConnectionError.
        """
        _LOGGER.info("Calibrating presets")
        aspect_ratios = parse_aspects(presets_aspect)
        motor_positions = [0.0] * len(aspect_ratios)
        for ar in aspect_ratios:
            self._motion_event.clear()
            self._stop_event.clear()
            await self.send_recall(ar["preset"])
            if await self._wait_polling(self._motion_event, CVM_MOTION_TIMEOUT):
                if not await self._wait_polling(self._stop_event, CVM_CALIBRATE_TIMEOUT):
                    raise TimeoutError(f"Motor didn't stop after recalling preset {ar['preset']}")
                await asyncio.sleep(CVM_SETTLE_TIME)
            else:
                _LOGGER.debug("Preset %d didn't move the motor; assuming it's already there", ar["preset"])
            position = await self.async_read_position()
            _LOGGER.info("Calibrated %s preset=%d motor=%.2f", ar["name"], ar["preset"], position)
            motor_positions[ar["preset"]-1] = position
        _LOGGER.info("Calibration complete")
        return ",".join([str(p) for p in motor_positions])

    async def async_init(self, data_callback: Callable[[dict], None]) -> dict:
        """Query position and wait for response."""
        self._callback = data_callback
        await self.send_query_position()
        await asyncio.wait_for(
            self._init_event.wait(),
            timeout=CVM_LOGIN_TIMEOUT
        )
        return self._data

    def _notify(self) -> None:
        """Pass the current data to the listener."""
        if self._callback is not None:
            self._callback(self._data)

    async def listener(self) -> None:
        """Listen for status updates from device."""

        while True:
            try:
                line = await self._reader.readuntil(b"\n")

                _LOGGER.debug("<- %s", str(line))
                if line.strip() == b"":
                    continue

                match = self._match_re.match(line)
                if match is None:
                    if line.startswith(b"!UID"):
                        # The e-Node echoes its CS-Bus config (SHADOW/QUALIFY/ACTION tables) to
                        # every telnet session, e.g. after a reconnect or while its web pages are open.
                        _LOGGER.debug("e-Node config line ignored: %s", line)
                    else:
                        _LOGGER.warning("Unexpected screen response: %s", line)
                    continue

                if match.group(1) == b'#' and match.group(4) == b"RECALL":
                    _LOGGER.debug("screen moving")
                    self._is_moving = True
                elif match.group(1) == b'!':
                    if match.group(3) == b".POSITION" and match.group(2) == b"1":
                        motor_position = float(match.group(4))
                        if motor_position == self._data["motor_position"]:
                            self._is_moving = False
                            if self._motion_event.is_set() and not self._stop_event.is_set():
                                _LOGGER.debug("Position not changed, assuming motor stopped")
                                self._stop_event.set()
                        else:
                            if self._data["motor_position"] is not None:
                                self._motion_event.set()
                            ar = self.motor_position_to_aspect(motor_position)
                            _LOGGER.debug("Mask position: motor=%.2f position=%d aspect=%s preset=%d",
                                          motor_position, ar["cover_position"], ar["name"], ar["preset"])
                            self._data["cover_position"] = ar["cover_position"]
                            self._data["motor_position"] = motor_position
                            self._data["screen_aspect_ratio"] = ar["value"]
                            self._data["screen_aspect_ratio_string"] = ar["name"]
                            self._data["screen_preset"] = ar["preset"]
                            self._init_event.set()
                            self._notify()
                        self._position_event.set()
                    elif match.group(3) == b".STATUS":
                        status = str(match.group(4), encoding='ascii')
                        if status == "STOP":
                            _LOGGER.debug("Motor %s stopped", str(match.group(2), encoding='ascii'))
                            self._is_moving = False
                            if self._motion_event.is_set():
                                self._stop_event.set()
                        else:
                            self._motion_event.set()
                        if status != self._data["motor_status"]:
                            _LOGGER.debug("Mask status: %s", status)
                            self._data["motor_status"] = status
                            self._notify()

            except (asyncio.IncompleteReadError, ConnectionResetError) as err:
                _LOGGER.warning("Connection to %s lost: %r", self._host, err)
                break

            except Exception:
                _LOGGER.exception("Unexpected read error")
                break

        self._online = False
        self._writer.close()
        self._notify()
