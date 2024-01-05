from homeassistant.helpers.device_registry import DeviceInfo

from ....api.platform.sensor.sensor import Sensor
from ....api.platform.sensor.sensor_description import SensorDescription
from .boiler_energy_sensor import KWBBoilerEnergySensor


class KWBPelletConsumptionSensor(Sensor):
    """Calculate lifetime pellet consumption."""

    def __init__(
        self,
        entity_description: SensorDescription,
        device_info: DeviceInfo,
        pellet_energy: float,
        boiler_energy_sensor: KWBBoilerEnergySensor,
    ):
        super().__init__(entity_description=entity_description, device_info=device_info)

        self._attr_available = False
        self._attr_should_poll = True
        self.pellet_energy = pellet_energy
        self.boiler_energy_sensor = boiler_energy_sensor

    async def async_update(self):
        """Update sensor value."""

        if not self.boiler_energy_sensor.state:
            return

        boiler_energy: int = self.boiler_energy_sensor.state
        self._attr_native_value = boiler_energy / self.pellet_energy
        self._attr_available = True
