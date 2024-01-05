from datetime import datetime, timedelta
import logging

from homeassistant.helpers.device_registry import DeviceInfo

from ....api.platform.sensor.sensor import Sensor
from ....api.platform.sensor.sensor_coordinated import CoordinatedSensor
from ....api.platform.sensor.sensor_description import SensorDescription

logger = logging.getLogger(__name__)


class CalculatedSensor(Sensor):
    """A sensor that calculates its own values.

    Do not do any IO in this class.
    """

    @property
    def native_value(self):
        """Calculate and return the native value of the sensor.

        Do not do any IO in this method.
        """
        return self._attr_native_value
