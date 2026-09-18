"""Support for KWB Heater flags."""

from typing import override

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from pykwb import kwb

from . import KWBConfigEntry
from .entity import KWBEntity


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Add flags using the connection opened by the legacy sensor platform."""
    if discovery_info is None:
        return
    client = discovery_info["client"]
    add_entities(
        KWBBinarySensor(client, sensor, discovery_info[CONF_NAME])
        for sensor in client.get_sensors()
        if sensor.sensor_type == kwb.PROP_SENSOR_FLAG
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KWBConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add flags for a UI-configured heater."""
    client = entry.runtime_data
    async_add_entities(
        KWBBinarySensor(client, sensor, entry.data[CONF_NAME], entry.entry_id)
        for sensor in client.get_sensors()
        if sensor.sensor_type == kwb.PROP_SENSOR_FLAG
    )


class KWBBinarySensor(KWBEntity, BinarySensorEntity):
    """Representation of a KWB Heater flag."""

    @property
    @override
    def is_on(self) -> bool | None:
        """Return the flag state, or unknown before a value is available."""
        if self._sensor.value is None or not self._sensor.available:
            return None
        return bool(self._sensor.value)
