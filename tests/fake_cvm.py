"""A fake CVM telnet server that follows the controller's line protocol."""

from __future__ import annotations

import asyncio
import re

PRESET_POSITIONS = [5.79, 1.76, 5.06, 0.0, 3.52, 8.64]


class FakeCVM:
    """Serves login, position queries, preset recall, retract and stop.

    Recalled presets start moving after ``start_delay`` s, stepping ``step`` per
    ``tick`` s, bracketed by STATUS pushes. Position is only reported when queried.
    """

    def __init__(self, password: str = "pass", position: float = 3.52) -> None:
        self.password = password
        self.position = position
        self.status = "STOP"
        self.start_delay = 0.0
        self.step = 0.5
        self.tick = 0.02
        self.clients: list[asyncio.StreamWriter] = []
        self._all: list[asyncio.StreamWriter] = []
        self.commands: list[str] = []
        self.port = 0
        self._server: asyncio.Server | None = None
        self._motion: asyncio.Task | None = None

    @property
    def open_clients(self) -> int:
        return sum(1 for w in self.clients if not w.is_closing())

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._client, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._motion:
            self._motion.cancel()
        for writer in self._all:
            writer.close()
        self._server.close()
        await self._server.wait_closed()

    def _broadcast(self, line: str) -> None:
        for writer in self.clients:
            if not writer.is_closing():
                writer.write(line.encode() + b"\r\n")

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._all.append(writer)
        writer.write(b"User:")
        await reader.readuntil(b"\r")
        writer.write(b"Password:")
        password = (await reader.readuntil(b"\r")).strip().decode()
        if password != self.password:
            await reader.read()  # never confirm; wait for the client to give up
            return
        writer.write(b"Connected:\r\n")
        self.clients.append(writer)
        try:
            while True:
                line = (await reader.readuntil(b"\n")).strip().decode()
                self.commands.append(line)
                self._handle(line, writer)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            writer.close()

    def _handle(self, line: str, writer: asyncio.StreamWriter) -> None:
        if line == "#1.1.1.MOTOR.POSITION=?":
            writer.write(f"!1.1.1.MOTOR.POSITION={self.position:.2f}\r\n".encode())
        elif match := re.fullmatch(r"#1\.1\.0\.MOTOR=RECALL,(\d+);", line):
            writer.write(f"{line}\r\n".encode())
            self._move_to(PRESET_POSITIONS[int(match.group(1)) - 1])
        elif line == "#1.1.0.MOTOR=RETRACT;":
            self._move_to(0.0)
        elif line == "#1.1.0.MOTOR=STOP;" and self._motion:
            self._motion.cancel()
            self._set_status("STOP")

    def _set_status(self, status: str) -> None:
        self.status = status
        self._broadcast(f"!1.1.1.MOTOR.STATUS={status}")

    def _move_to(self, target: float) -> None:
        if self._motion:
            self._motion.cancel()
        if target != self.position:
            self._motion = asyncio.get_running_loop().create_task(self._run(target))

    async def _run(self, target: float) -> None:
        await asyncio.sleep(self.start_delay)
        self._set_status("EXTENDING" if target > self.position else "RETRACTING")
        while abs(target - self.position) > self.step:
            self.position += self.step if target > self.position else -self.step
            await asyncio.sleep(self.tick)
        self.position = target
        self._set_status("STOP")
