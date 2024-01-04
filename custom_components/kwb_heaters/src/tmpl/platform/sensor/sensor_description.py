from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntityDescription


@dataclass
class SensorDescription(SensorEntityDescription):
    """Describe sensor entity properties.

    Any custom properties should go here as class attributes.
    """
