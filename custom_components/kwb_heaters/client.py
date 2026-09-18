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


def create_client(config: Mapping[str, Any], *, reconnect: bool = True) -> KWBClient:
    """Open the configured connection (must run in an executor)."""
    if config[CONF_TYPE] == "serial":
        return KWBClient(kwb.PROP_MODE_SERIAL, _serial_device=config[CONF_DEVICE])
    return KWBClient(
        kwb.PROP_MODE_TCP,
        config[CONF_HOST],
        config[CONF_PORT],
        _config={"connection": {"reconnect": reconnect}},
    )


def validate_connection(config: Mapping[str, Any]) -> None:
    """Check that the transport can be opened, without starting a reader."""
    # A failed setup probe must raise instead of waiting for background retries.
    client = create_client(config, reconnect=False)
    client._close_connection()
