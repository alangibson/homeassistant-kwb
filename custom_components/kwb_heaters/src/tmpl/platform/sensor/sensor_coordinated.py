import logging
from homeassistant.const import CONF_UNIQUE_ID

from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .....const import DOMAIN, MANUFACTURER
from .sensor import Sensor
from .sensor_description import SensorDescription

logger = logging.getLogger(__name__)


class CoordinatedSensor(CoordinatorEntity, Sensor):
    """Sensor that is updated by DataUpdateCoordinator."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        description: SensorDescription,
        device_info: DeviceInfo,
    ):
        """Initialize the sensor.

        You must super().__init__(coordinator) in this method in order for
        polling to work.
        """
        super().__init__(coordinator)

        unique_device_id = list(device_info.get("identifiers"))[0][1]

        self._attr_available = True
        self._attr_unique_id = f"kwb_{unique_device_id}_{description.key}"
        self._attr_device_info = device_info

        # SensorEntity superclass will automatically pull sensor
        # values from entity_description
        self.entity_description = description

    @property
    def native_value(self):
        """Return the native value of the sensor based on the last data poll.

        You could also set self._attr_native_value in self._handle_coordinator_update()
        instead of implementing this method.
        """
        return self.coordinator.data.latest_scrape[self.entity_description.key]

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update entity value(s) from data update coordinator.

        # Put transformations here, such as setting self._attr_native_value
        or setting self._attr_available = True

        If super()._handle_coordinator_update() is not called, then the
        state will not be saved to HomeAssistant.
        """

        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """Sensor is loaded into HomeAssistant.

        Do anything that needs to happen at the time the sensor is
        loaded here.

        If the super().async_added_to_hass() is not called,
        then sensor values will not be updated.
        """

        await super().async_added_to_hass()
