"""Support for KWB Easyfire."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_MODEL, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, MANUFACTURER
from .src.impl.config.sensor.entities import setup_entities

logger = logging.getLogger(__name__)


# Called automagically by Home Assistant
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Transform ConfigEntry into sensor entities.

    Required by HomeAssistant
    """
    # Retrieve data update coordinator
    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id].get(
        "coordinator"
    )

    unique_device_id = config_entry.data.get(CONF_UNIQUE_ID)
    model = config_entry.data.get(CONF_MODEL)

    device_info: DeviceInfo = {
        "identifiers": {(DOMAIN, unique_device_id)},
        "manufacturer": MANUFACTURER,
        "name": f"{MANUFACTURER} {model}",
        "model": model,
    }

    # TODO make create_sensors composable.
    # Can we allow devs to inject it by setting
    #   hass.data[DOMAIN][...]['f_create_sensors'] = ... ?

    # Register our sensor entities.
    # create_sensors() can return any kind of Iterable.
    async_add_entities(
        setup_entities(
            device_info=device_info, coordinator=coordinator, config_entry=config_entry
        ),
        update_before_add=True,
    )
