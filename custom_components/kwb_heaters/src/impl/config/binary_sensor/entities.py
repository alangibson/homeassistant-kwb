from collections.abc import Iterable
import logging

from pykwb.kwb import load_signal_maps
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ....api.platform.binary_sensor.binary_sensor_coordinated import (
    CoordinatedBinarySensor,
)
from ....api.platform.binary_sensor.binary_sensor_description import (
    BinarySensorDescription,
)

logger = logging.getLogger(__name__)


def setup_entities(
    device_info: DeviceInfo,
    coordinator: DataUpdateCoordinator,
    config_entry: ConfigEntry,
) -> Iterable[Entity]:
    """Transform pykwb signal maps into KWBSensorEntityDescriptions.

    Do not do any IO in this method. It is not async and so will
    block the HomeAssistant event loop.
    """

    # TODO refactor out this chunk. Same in sensors.entities.py
    unique_device_id = list(device_info.get("identifiers"))[0][1]
    model = device_info.get("model")

    entities = []

    # TODO refactor out this chunk. Same in sensors.entities.py
    for signal_map in load_signal_maps(source=10):
        if not signal_map:
            continue
        for signal_key, signal_definition in signal_map.items():
            sensor_key = (
                signal_definition[5]
                if signal_definition[5] and signal_definition[5] != ""
                else signal_key.lower().replace(" ", "_")
            )
            # TODO signal_key is a key, not a name. Translate it
            sensor_name = f"{model} {unique_device_id} {signal_key}"

            if signal_definition[0] == "b":
                # TODO should be from BinarySensorDeviceClass.
                # Should be "running" or "problem"?
                # device_class = signal_definition[5]

                entities.append(
                    CoordinatedBinarySensor(
                        coordinator=coordinator,
                        device_info=device_info,
                        entity_description=BinarySensorDescription(
                            key=sensor_key,
                            translation_key=sensor_key,
                            name=sensor_name,
                            device_class=BinarySensorDeviceClass.RUNNING,
                        ),
                    )
                )

    entities.append(
        CoordinatedBinarySensor(
            coordinator=coordinator,
            device_info=device_info,
            entity_description=BinarySensorDescription(
                key="boiler_on",
                translation_key="boiler_on",
                name=f"{model} {unique_device_id} Boiler On",
                device_class=BinarySensorDeviceClass.RUNNING,
            ),
        )
    )

    return entities
