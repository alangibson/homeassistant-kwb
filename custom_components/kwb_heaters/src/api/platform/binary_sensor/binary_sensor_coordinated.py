import logging

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .binary_sensor import BinarySensor
from .binary_sensor_description import BinarySensorDescription

logger = logging.getLogger(__name__)


class CoordinatedBinarySensor(CoordinatorEntity, BinarySensor):
    """Custom binary sensor entity."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entity_description: BinarySensorDescription,
        device_info: DeviceInfo,
    ):
        super().__init__(coordinator)

        unique_device_id = list(device_info.get("identifiers"))[0][1]

        self._attr_available = True
        self._attr_unique_id = f"kwb_{unique_device_id}_{entity_description.key}"
        self._attr_device_info = device_info

        self.entity_description = entity_description

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.latest_scrape[self.entity_description.key])

    # @callback
    # def _handle_coordinator_update(self) -> None:
    #     """Update entity value(s) from data update coordinator.

    #     # Put transformations here, such as setting self._attr_is_on
    #     or setting self._attr_available = True

    #     If super()._handle_coordinator_update() is not called, then the
    #     state will not be saved to HomeAssistant.
    #     """

    #     super()._handle_coordinator_update()

    # async def async_added_to_hass(self) -> None:
    #     """Sensor is loaded into HomeAssistant.

    #     Do anything that needs to happen at the time the sensor is
    #     loaded here.

    #     If the super().async_added_to_hass() is not called,
    #     then sensor values will not be updated.
    #     """

    #     await super().async_added_to_hass()
