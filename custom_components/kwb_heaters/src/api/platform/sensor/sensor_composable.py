from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
import logging

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorEntity,
    SensorEntityDescription,
    SensorExtraStoredData,
)
from homeassistant.core import State, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .sensor_composable_defaults import (
    GetAvailableFunction,
    GetNativeValueFunction,
    GetUniqueSensorIdFunction,
    RestoreNativeValueFunction,
    UndefinedBehaviorFunction,
)
from .sensor_composable_types import (
    GetAvailableType,
    GetNativeValueType,
    GetUniqueSensorIdType,
    RestoreNativeValueType,
    UndefinedBehaviorType,
)

logger = logging.getLogger(__name__)


class EntityPersona:
    CLOUD_POLL = "cloud_poll"
    LOCAL_POLL = "local_poll"


class ComposableSensorDescription(SensorEntityDescription):
    # Restore sensor value on load?
    restore: bool = False
    # Polled by DataUpdateCoordinator
    coordinated: bool = True
    # persona: EntityPersona = EntityPersona.LOCAL_PUSH

    f_get_unique_sensor_id: GetUniqueSensorIdType = GetUniqueSensorIdFunction
    f_get_native_value: GetNativeValueType = GetNativeValueFunction
    f_get_available: GetAvailableType = GetAvailableFunction
    f_on_init: UndefinedBehaviorType = UndefinedBehaviorFunction
    f_on_poll_update: UndefinedBehaviorType = UndefinedBehaviorFunction
    f_on_loaded: UndefinedBehaviorType = UndefinedBehaviorFunction
    f_on_restore_state: UndefinedBehaviorType = UndefinedBehaviorFunction
    f_on_coordinator_update: UndefinedBehaviorType = UndefinedBehaviorFunction
    f_restore_native_value: RestoreNativeValueType = RestoreNativeValueFunction


class ComposableSensor(CoordinatorEntity, RestoreSensor):
    def __init__(
        self,
        entity_description: ComposableSensorDescription,
        device_info: DeviceInfo,
        coordinator: DataUpdateCoordinator = None,
    ):
        """Initialize the sensor."""

        # You must super().__init__(coordinator) in this method in order for
        # polling to work.
        super().__init__(coordinator)

        # Log warnings if configuration seems odd
        if entity_description.coordinated and not coordinator:
            logger.warning(
                "Description specified coordinated==True, but no coordinator provided"
            )
        if not entity_description.coordinated and coordinator:
            logger.warning(
                "Description specified coordinated==False, but a coordinator was provided"
            )

        self._attr_device_info = device_info

        # self.entity_description is defined on Entity superclass.
        # Superclass will automatically get settings from entity_description.
        self.entity_description: ComposableSensorDescription = entity_description

        self._attr_unique_id = self.entity_description.f_get_unique_sensor_id(self)

        self._attr_should_poll = not self.entity_description.coordinated

        self.entity_description.f_on_init(self)

    async def async_update(self):
        """Update sensor value.

        If you need to do IO, and you are not using a DataUpdateCoordinator,
        then do it here.

        Only called when self.coordinator = None
        """

        if self.entity_description.coordinated:
            logger.warning("async_update called but coordinated==True")

        # Set the native value here
        self._attr_native_value = self.entity_description.f_get_native_value(self)
        # and the availability
        self._attr_available = self.entity_description.f_get_available(self)

        self.entity_description.f_on_poll_update(self)

    async def async_added_to_hass(self) -> None:
        """Recover last state."""

        if self.entity_description.restore:
            # Do state recovery
            data: SensorExtraStoredData | None = await self.async_get_last_sensor_data()
            state: State | None = await self.async_get_last_state()
            self._attr_native_value = self.entity_description.f_restore_native_value(
                self, data, state
            )
            self.entity_description.f_on_restore_state(self)

        self.entity_description.f_on_loaded(self)

        await super().async_added_to_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update entity value(s) from data update coordinator.

        # Put transformations here, such as setting self._attr_native_value
        or setting self._attr_available = True

        If super()._handle_coordinator_update() is not called, then the
        state will not be saved to HomeAssistant.
        """

        if not self.entity_description.coordinated:
            logger.warning("_handle_coordinator_update called but coordinated==False")

        self._attr_native_value = self.entity_description.f_get_native_value(self)

        self.entity_description.f_on_coordinator_update(self)

        super()._handle_coordinator_update()

    @property
    def native_value(self):
        """Return the native value of the sensor based on the last data poll.

        You could also set self._attr_native_value in self._handle_coordinator_update()
        instead of implementing this method.
        """
        return self.entity_description.f_get_native_value(self)

    # @property
    # def should_poll(self) -> bool:
    #     """Tell HA generic poller if it should poll by calling async_update.

    #     If a sensor is coordinated by DataUpdateCoordinator, then it
    #     should not be polled.
    #     """
    #     return not self.entity_description.coordinated
