from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal

from homeassistant.components.sensor import SensorExtraStoredData
from homeassistant.core import State
from homeassistant.helpers.typing import StateType

from .sensor_composable import ComposableSensor

NativeValueType = StateType | date | datetime | Decimal

UndefinedBehaviorType = Callable[[ComposableSensor], None]
GetUniqueSensorIdType = Callable[[ComposableSensor], str]
GetAvailableType = Callable[[ComposableSensor], bool]
GetNativeValueType = Callable[[ComposableSensor], NativeValueType]
RestoreNativeValueType = Callable[
    [ComposableSensor, SensorExtraStoredData | None, State | None],
    NativeValueType,
]
