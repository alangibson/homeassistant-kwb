from __future__ import annotations

from collections.abc import Iterable
import logging

from pykwb.kwb import load_signal_maps

from homeassistant.components.sensor.const import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower, UnitOfTime
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .....const import CONF_BOILER_EFFICIENCY, CONF_BOILER_NOMINAL_POWER
from ....impl.platform.sensor.boiler_energy_sensor import KWBBoilerEnergySensor
from ....tmpl.platform.sensor.sensor_coordinated import CoordinatedSensor
from ....tmpl.platform.sensor.sensor_description import SensorDescription

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

    unique_device_id = list(device_info.get("identifiers"))[0][1]
    model = device_info.get("model")

    # We will need these for later use at the end
    boiler_nominal_power: float = config_entry.data.get(CONF_BOILER_NOMINAL_POWER)
    boiler_efficiency: float = config_entry.data.get(CONF_BOILER_EFFICIENCY)
    boiler_output_sensor: CoordinatedSensor = None

    entities = []

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

            if signal_definition[0] != "b":
                unit = signal_definition[4]
                state_class = signal_definition[6]
                device_class = signal_definition[7]

                sensor = CoordinatedSensor(
                    coordinator=coordinator,
                    device_info=device_info,
                    description=SensorDescription(
                        key=sensor_key,
                        translation_key=sensor_key,
                        name=sensor_name,
                        native_unit_of_measurement=unit,
                        device_class=device_class,
                        state_class=state_class,
                    ),
                )

                if sensor_key == "boiler_output":
                    boiler_output_sensor = sensor

                entities.append(sensor)

    entities.append(
        CoordinatedSensor(
            coordinator=coordinator,
            device_info=device_info,
            description=SensorDescription(
                key="boiler_nominal_power",
                translation_key="boiler_nominal_power",
                name=f"{model} {unique_device_id} Boiler Nominal Power",
                native_unit_of_measurement=UnitOfPower.KILO_WATT,
                device_class=SensorDeviceClass.POWER,
                state_class=state_class,
            ),
        )
    )
    entities.append(
        CoordinatedSensor(
            coordinator=coordinator,
            device_info=device_info,
            description=SensorDescription(
                key="boiler_power",
                translation_key="boiler_power",
                name=f"{model} {unique_device_id} Boiler Power",
                native_unit_of_measurement=UnitOfPower.KILO_WATT,
                device_class=SensorDeviceClass.POWER,
                state_class=state_class,
            ),
        )
    )
    entities.append(
        CoordinatedSensor(
            coordinator=coordinator,
            device_info=device_info,
            description=SensorDescription(
                key="boiler_run_time",
                translation_key="boiler_run_time",
                name=f"{model} {unique_device_id} Boiler Run Time",
                native_unit_of_measurement=UnitOfTime.SECONDS,
                device_class=SensorDeviceClass.DURATION,
                state_class=state_class,
            ),
        )
    )
    entities.append(
        CoordinatedSensor(
            coordinator=coordinator,
            device_info=device_info,
            description=SensorDescription(
                key="pellet_consumption",
                translation_key="pellet_consumption",
                name=f"{model} {unique_device_id} Pellet Consumption",
                native_unit_of_measurement="kg",
                device_class=SensorDeviceClass.WEIGHT,
                state_class=state_class,
            ),
        )
    )
    entities.append(
        CoordinatedSensor(
            coordinator=coordinator,
            device_info=device_info,
            description=SensorDescription(
                key="last_timestamp",
                translation_key="last_timestamp",
                name=f"{model} {unique_device_id} Last Timestamp",
                native_unit_of_measurement=UnitOfTime.MILLISECONDS,
                device_class=SensorDeviceClass.DURATION,
                state_class=state_class,
            ),
        )
    )

    # HACK Create KWBBoilerEnergySensor
    # boiler_nominal_power = config_entry.data.get(CONF_BOILER_NOMINAL_POWER)
    # boiler_efficiency = config_entry.data.get(CONF_BOILER_EFFICIENCY)
    # boiler_output_sensor = list(
    #     filter(lambda e: e.entity_description.key == "boiler_output", entities)
    # ).pop()

    boiler_energy_sensor = KWBBoilerEnergySensor(
        device_info=device_info,
        boiler_nominal_power=boiler_nominal_power,
        boiler_efficiency=boiler_efficiency,
        boiler_output_sensor=boiler_output_sensor,
        entity_description=SensorDescription(
            key="boiler_energy_output",
            translation_key="boiler_energy_output",
            name=f"{model} {unique_device_id} Boiler Energy Output",
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL,
        ),
    )
    entities.append(boiler_energy_sensor)

    return entities
