import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_MODEL, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)

from .const import DOMAIN, MANUFACTURER
from .src.impl.config.binary_sensor.entities import setup_entities

logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize config entry."""

    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id].get(
        "coordinator"
    )

    unique_device_id = config_entry.data.get(CONF_UNIQUE_ID)
    model = config_entry.data.get(CONF_MODEL)

    # TODO this is repeated in sensor.py
    # Create a device info object
    device_info: DeviceInfo = {
        "identifiers": {(DOMAIN, unique_device_id)},
        "manufacturer": MANUFACTURER,
        "name": f"{MANUFACTURER} {model}",
        "model": model,
    }

    async_add_entities(
        setup_entities(
            coordinator=coordinator, config_entry=config_entry, device_info=device_info
        ),
        update_before_add=True,
    )
