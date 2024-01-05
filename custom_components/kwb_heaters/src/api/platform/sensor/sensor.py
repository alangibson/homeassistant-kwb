import logging

from homeassistant.components.sensor import RestoreSensor, SensorExtraStoredData
from homeassistant.core import State
from homeassistant.helpers.device_registry import DeviceInfo

from .sensor_description import SensorDescription

logger = logging.getLogger(__name__)


# TODO move to config
DEFAULT_RESTORE_SENSOR = True


class Sensor(RestoreSensor):
    """Representation of a KWB Easyfire sensor."""

    _recovered = False

    def __init__(self, entity_description: SensorDescription, device_info: DeviceInfo):
        unique_device_id = list(device_info.get("identifiers"))[0][1]

        self._attr_unique_id = f"kwb_{unique_device_id}_{entity_description.key}"
        self._attr_device_info = device_info

        self.entity_description = entity_description

    async def async_added_to_hass(self) -> None:
        """Recover last state"""

        await super().async_added_to_hass()

        #
        # Restore saved sensor value
        #

        if not DEFAULT_RESTORE_SENSOR:
            return

        state: State | None = await self.async_get_last_state()

        data: SensorExtraStoredData | None = await self.async_get_last_sensor_data()
        if not data:
            return

        logger.debug(
            "Recovered state for %s is %s %s",
            self.entity_description.key,
            data.native_value,
            data.native_unit_of_measurement,
        )

        self._attr_native_value = data.native_value
        self._recovered = True

        self.async_schedule_update_ha_state(True)
