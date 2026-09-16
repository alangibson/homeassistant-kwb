"""Manage the shared asynchronous pykwb listener and connection."""

import asyncio
import logging
import socket
from collections.abc import Mapping
from contextlib import suppress
from typing import Any

from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT, CONF_TYPE
from homeassistant.core import HomeAssistant
from pykwb import kwb

from .const import CONNECTION_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class KWBClient(kwb.KWBEasyfire):
    """A pykwb client with bounded TCP connection setup and explicit cleanup."""

    def _open_connection(self) -> None:
        if self._mode == kwb.PROP_MODE_TCP:
            self._socket = socket.create_connection(
                (self._ip, self._port), timeout=CONNECTION_TIMEOUT
            )
            self._socket.settimeout(None)
        else:
            super()._open_connection()

    def _close_connection(self) -> None:
        # pykwb also calls this from its destructor, including after failed setup.
        if sock := getattr(self, "_socket", None):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        if serial_port := getattr(self, "_serial", None):
            serial_port.close()

    _listener_task: asyncio.Task[None] | None = None

    async def listen_forever(self) -> None:
        """Surface EOF so the bounded listener cannot spin on a closed socket."""
        await super().listen_forever()
        raise EOFError("KWB connection closed")

    async def _async_listen(self, hass: HomeAssistant) -> None:
        """Continuously update shared sensors using pykwb's bounded async API."""
        try:
            while True:
                await self.listen_for(seconds=60)
        except OSError, EOFError:
            _LOGGER.exception("KWB connection closed while reading")
        finally:
            for sensor in self.get_sensors():
                sensor.value = None
            await hass.async_add_executor_job(self._close_connection)

    def async_start(self, hass: HomeAssistant) -> None:
        """Start a single listener without a pykwb reader thread."""
        self._listener_task = hass.async_create_background_task(
            self._async_listen(hass), "KWB listener"
        )

    async def async_stop(self, hass: HomeAssistant) -> None:
        """Cancel reads before closing the transport in the executor."""
        if self._listener_task is not None:
            self._listener_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._listener_task
            self._listener_task = None
        # Also handles a task cancelled before its coroutine first ran.
        await hass.async_add_executor_job(self._close_connection)


def create_client(config: Mapping[str, Any]) -> KWBClient:
    """Open the configured connection (must run in an executor)."""
    if config[CONF_TYPE] == "serial":
        return KWBClient(kwb.PROP_MODE_SERIAL, _serial_device=config[CONF_DEVICE])
    return KWBClient(kwb.PROP_MODE_TCP, config[CONF_HOST], config[CONF_PORT])


def validate_connection(config: Mapping[str, Any]) -> None:
    """Check that the transport can be opened, without starting a reader."""
    client = create_client(config)
    client._close_connection()
