"""The KWB integration"""

import logging

from homeassistant.config_entries import (
    ConfigEntry,
    OptionsFlow
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .config_flow import KWBOptionsFlow
from .const import DOMAIN

logger = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Entry point to set up KWB heaters"""

    hass_data = dict(config_entry.data)

    # Register options flow
    # Registers update listener to update config entry when options are updated.
    unsub_options_update_listener = config_entry.add_update_listener(options_update_listener)
    # Store a reference to the unsubscribe function to cleanup if an entry is unloaded.
    hass_data["unsub_options_update_listener"] = unsub_options_update_listener
    hass.data[DOMAIN][config_entry.entry_id] = hass_data

    # Forward the setup to the sensor platform.
    hass.async_create_task(
        # For platform 'sensor', file sensor.py must exist
        hass.config_entries.async_forward_entry_setup(config_entry, Platform.SENSOR)
    )

    return True


# @staticmethod
# @callback
# def async_get_options_flow(
#     config_entry: ConfigEntry,
# ) -> OptionsFlow:
#     """Create the options flow."""
#     return KWBOptionsFlow(config_entry)


async def options_update_listener(
    hass: HomeAssistant, config_entry: ConfigEntry
):
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)


# TODO Unload gracefully
# https://github.com/home-assistant/core/blob/dev/homeassistant/components/fronius/__init__.py
# async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
#   ...