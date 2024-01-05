from datetime import date, datetime
from decimal import Decimal

from homeassistant.components.sensor import SensorExtraStoredData
from homeassistant.core import State
from homeassistant.helpers.typing import StateType

from .sensor_composable import ComposableSensor


class UndefinedBehaviorFunction:
    """Expected behavior is not defined."""

    def __call__(self: ComposableSensor) -> None:
        """Do whatever with self and return nothing."""
        return


class GetUniqueSensorIdFunction:
    """"""

    def __call__(self: ComposableSensor) -> str:
        """Return unique id for this sensor.

        Type is taken from Entity._attr_unique_id
        """
        raise NotImplementedError("Please implement GetUniqueSensorIdFunction")


class GetAvailableFunction:
    def __call__(self: ComposableSensor) -> bool:
        """Return True if sensor is available, False otherwise.

        Type is taken from Entity._attr_available.
        Defaults to True because this is the HomeAssistant default.
        """
        return True


class GetNativeValueFunction:
    def __call__(self: ComposableSensor) -> StateType | date | datetime | Decimal:
        """Return native value of a sensor.

        Type is taken from SensorEntity._attr_native_value
        """
        raise NotImplementedError("Please implement GetNativeValueFunction")


class RestoreNativeValueFunction:
    def __call__(
        self: ComposableSensor,
        data: SensorExtraStoredData | None = None,
        state: State | None = None,
    ) -> StateType | date | datetime | Decimal:
        """Return native value of a sensor.

        Type is taken from SensorEntity._attr_native_value
        """
        return data.native_value
