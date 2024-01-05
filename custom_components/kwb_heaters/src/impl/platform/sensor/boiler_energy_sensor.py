from datetime import datetime, timedelta
import logging

from homeassistant.helpers.device_registry import DeviceInfo

from ....api.platform.sensor.sensor import Sensor
from ....api.platform.sensor.sensor_coordinated import CoordinatedSensor
from ....api.platform.sensor.sensor_description import SensorDescription

logger = logging.getLogger(__name__)


class KWBBoilerEnergySensor(Sensor):
    """Calculate lifetime boiler power production."""

    def __init__(
        self,
        entity_description: SensorDescription,
        boiler_nominal_power: float,
        boiler_efficiency: float,
        boiler_output_sensor: CoordinatedSensor,
        device_info: DeviceInfo,
    ):
        super().__init__(entity_description=entity_description, device_info=device_info)

        self._attr_available = True

        self.last_timestamp = datetime.now()
        self.boiler_nominal_power = boiler_nominal_power
        self.boiler_efficiency = boiler_efficiency
        self.boiler_output_sensor = boiler_output_sensor

    async def async_update(self):
        """Update sensor value."""

        if not self._recovered:
            # Don't do an update until state recovery has finished
            return

        if not self.boiler_output_sensor.state:
            return

        elapse_time: timedelta = datetime.now() - self.last_timestamp
        elapse_hr: float = elapse_time.total_seconds() / 60 / 60
        boiler_output: int = self.boiler_output_sensor.state
        boiler_output_factor: float = boiler_output / 100
        boiler_nominal_power_kW = self.boiler_nominal_power
        boiler_power_kW = boiler_nominal_power_kW * boiler_output_factor
        delta_boiler_energy_kWh = boiler_power_kW * elapse_hr

        current_value = self._attr_native_value if self._attr_native_value else 0.0
        self._attr_native_value = current_value + delta_boiler_energy_kWh

        self._attr_available = True

        self.last_timestamp = datetime.now()
