"""The KWB integration"""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

logger = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Entry point to set up KWB heaters"""

    # Forward the setup to the sensor platform.
    hass.async_create_task(
        # For platform 'sensor', file sensor.py must exist
        hass.config_entries.async_forward_entry_setup(config_entry, Platform.SENSOR)
    )
    return True


# TODO Unload gracefully
# https://github.com/home-assistant/core/blob/dev/homeassistant/components/fronius/__init__.py
# async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
#   ...