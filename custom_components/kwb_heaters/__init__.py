"""KWB Heaters integration."""

import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .client import KWBClient, create_client
from .const import PROPERTY_DEFAULTS

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.NUMBER, Platform.BUTTON]
type KWBConfigEntry = ConfigEntry[KWBClient]


async def async_setup_entry(hass: HomeAssistant, entry: KWBConfigEntry) -> bool:
    """Open the heater connection and set up its sensors."""
    missing = {
        key: value
        for key, value in PROPERTY_DEFAULTS.items()
        if entry.data.get(key) is None
    }
    if missing:
        hass.config_entries.async_update_entry(entry, data={**entry.data, **missing})
    try:
        client = await hass.async_add_executor_job(create_client, entry.data)
    except OSError as err:
        raise ConfigEntryNotReady(f"Unable to connect to KWB heater: {err}") from err

    entry.runtime_data = client

    async def async_stop(event: Event) -> None:
        await client.async_stop(hass)

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_stop)
    )
    try:
        client.async_start(hass)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except (Exception, asyncio.CancelledError):
        await client.async_stop(hass)
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KWBConfigEntry) -> bool:
    """Unload sensors and release the connection."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.async_stop(hass)
    return True
