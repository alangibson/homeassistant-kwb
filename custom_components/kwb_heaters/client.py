"""Manage the shared asynchronous pykwb listener and connection."""

import asyncio
import logging
from collections.abc import Mapping
from contextlib import suppress
from typing import Any

from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT, CONF_TYPE
from homeassistant.core import HomeAssistant
from pykwb import kwb

_LOGGER = logging.getLogger(__name__)
PROBE_SECONDS = 10


class NoSensorsError(Exception):
    """The library returned no sensors after listening."""


class KWBClient(kwb.KWBEasyfire):
    """Adapt pykwb's listener to Home Assistant's task lifecycle."""

    _listener_task: asyncio.Task[None] | None = None

    async def _async_listen(self, hass: HomeAssistant) -> None:
        """Let pykwb manage reads, connection failures, and retries."""
        try:
            await self.listen_forever()
        except (OSError, EOFError):
            _LOGGER.exception("KWB connection closed while reading")
        finally:
            for sensor in self.get_sensors():
                sensor.value = None
            await self.close()

    def async_start(self, hass: HomeAssistant) -> None:
        """Start a single listener without a pykwb reader thread."""
        self._listener_task = hass.async_create_background_task(
            self._async_listen(hass), "KWB listener"
        )

    async def async_stop(self, hass: HomeAssistant) -> None:
        """Cancel reads before asynchronously closing the transport."""
        if self._listener_task is not None:
            self._listener_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._listener_task
            self._listener_task = None
        # Also handles a task cancelled before its coroutine first ran.
        await self.close()


def create_client(config: Mapping[str, Any], *, reconnect: bool = True) -> KWBClient:
    """Create the lazy transport and load sensor definitions in an executor."""
    if config[CONF_TYPE] == "serial":
        client = KWBClient(kwb.PROP_MODE_SERIAL, _serial_device=config[CONF_DEVICE])
    else:
        client = KWBClient(
            kwb.PROP_MODE_TCP,
            config[CONF_HOST],
            config[CONF_PORT],
            _config={"connection": {"reconnect": reconnect}},
        )
    client.load_sensors()
    return client


async def validate_connection(config: Mapping[str, Any]) -> None:
    """Listen briefly and require a non-empty sensor list."""
    client = await asyncio.to_thread(create_client, config, reconnect=False)
    try:
        await client.listen_for(PROBE_SECONDS)
        if not client.get_sensors():
            raise NoSensorsError
    finally:
        await client.close()
