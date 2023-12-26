"""Support for KWB Easyfire."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging

import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import (
    CONF_DEVICE,
    CONF_HOST,
    CONF_MODEL,
    CONF_NAME,
    CONF_PORT,
    CONF_PROTOCOL,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_TYPE,
    CONF_UNIQUE_ID,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.config_entries import ConfigEntry

from pykwb.kwb import load_signal_maps
from .const import (
    DOMAIN, 
    MIN_TIME_BETWEEN_UPDATES,
    CONF_PELLET_NOMINAL_ENERGY,
    CONF_BOILER_EFFICIENCY,
    CONF_BOILER_NOMINAL_POWER
)
from .heater import connect_heater, data_updater


logger = logging.getLogger(__name__)

DEFAULT_RAW = False
DEFAULT_NAME = "KWB"

MODE_SERIAL = 0
MODE_TCP = 1

CONF_RAW = "raw"

# TODO move these to config_flow.py
SERIAL_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_RAW, default=DEFAULT_RAW): cv.boolean,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_DEVICE): cv.string,
        vol.Required(CONF_TYPE): "serial",
    }
)
ETHERNET_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_RAW, default=DEFAULT_RAW): cv.boolean,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT): cv.port,
        vol.Required(CONF_TYPE): "tcp",
    }
)

PLATFORM_SCHEMA = vol.Schema(vol.Any(SERIAL_SCHEMA, ETHERNET_SCHEMA))


@dataclass
class KWBSensorEntityDescription(SensorEntityDescription):
    # register: str = None
    device_id: str = None
    device_model: str = None
    _original_name: str = None

    @property
    def original_name(self):
        """Capture original name since we will mutate name later"""
        if not self._original_name:
            self._original_name = self.name
        return self._original_name


class KWBSensor(SensorEntity):
    """Representation of a KWB Easyfire sensor."""

    def __init__(self, easyfire, sensor, client_name):
        """Initialize the KWB sensor."""
        self._easyfire = easyfire
        self._sensor = sensor
        self._client_name = client_name
        self._name = self._sensor.name

    @property
    def name(self):
        """Return the name."""
        return f"{self._client_name} {self._name}"

    @property
    def available(self) -> bool:
        """Return if sensor is available."""
        return self._sensor.available

    @property
    def native_value(self):
        """Return the state of value."""
        if self._sensor.value is not None and self._sensor.available:
            return self._sensor.value
        return None

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._sensor.unit_of_measurement


class KWBSensorEntity(CoordinatorEntity, SensorEntity):
    """Implementation of a KWB sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        description: KWBSensorEntityDescription,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)
        # SensorEntity superclass will automatically pull sensor values from entity_description
        self.entity_description = description

    @property
    def unique_id(self) -> str:
        if self._attr_unique_id:
            return self._attr_unique_id
        else:
            self._attr_unique_id = (
                f"kwb_{self.entity_description.device_id}_{self.entity_description.key}"
            )
            return self._attr_unique_id

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information about this IPP device."""
        if not self.entity_description.device_id:
            return None
        return DeviceInfo(
            identifiers={(DOMAIN, self.entity_description.device_id)},
            name=f"KWB {self.entity_description.device_model}",
            manufacturer="KWB",
            model=self.entity_description.device_model,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        sensor_key = self.entity_description.key
        return self.coordinator.data.latest_scrape[sensor_key]


def sensor_descriptions(unique_device_id, model):
    """Transsform pykwb signal maps into KWBSensorEntityDescriptions"""
    for signal_map in load_signal_maps(source=10):
        if not signal_map:
            continue
        for signal_key, signal_definition in signal_map.items():
            sensor_key = (
                signal_definition[5]
                if signal_definition[5] and signal_definition[5] != ""
                else signal_key.lower().replace(" ", "_")
            )
            model_slug = model.replace(".", "")
            # unique_device_key = unique_device_id.lower().replace(" ", "_")
            # TODO signal_key is a key, not a name. Translate it
            sensor_name = f"{model_slug} {unique_device_id} {signal_key}"

            if signal_definition[0] == "b":
                state_class = signal_definition[4]
                device_class = signal_definition[5]
                yield KWBSensorEntityDescription(
                    key=sensor_key,
                    translation_key=sensor_key,
                    name=sensor_name,
                    device_class=device_class,
                    state_class=state_class,
                    device_id=unique_device_id,
                    device_model=model,
                )
            else:
                unit = signal_definition[4]
                state_class = signal_definition[6]
                device_class = signal_definition[7]
                yield KWBSensorEntityDescription(
                    key=sensor_key,
                    translation_key=sensor_key,
                    name=sensor_name,
                    native_unit_of_measurement=unit,
                    device_class=device_class,
                    state_class=state_class,
                    device_id=unique_device_id,
                    device_model=model,
                )


# Called automagically by Home Assistant
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    # Get a unique id for the inverter device
    if (unique_device_id := config_entry.data.get(CONF_UNIQUE_ID)) is None:
        # unique_device_id = config_entry.entry_id
        raise Exception("Unique device id is None. This should not be possible.")

    # Setup sensors from a config entry created in the integrations UI
    # Configure KWB heater
    config_heater = {
        CONF_UNIQUE_ID: config_entry.data.get(CONF_UNIQUE_ID),
        CONF_HOST: config_entry.data.get(CONF_HOST),
        CONF_PORT: config_entry.data.get(CONF_PORT),
        CONF_TIMEOUT: int(config_entry.data.get(CONF_TIMEOUT)),
        CONF_MODEL: config_entry.data.get(CONF_MODEL),
        CONF_PROTOCOL: config_entry.data.get(CONF_PROTOCOL),
        CONF_BOILER_EFFICIENCY: config_entry.data.get(CONF_BOILER_EFFICIENCY),
        CONF_BOILER_NOMINAL_POWER: config_entry.data.get(CONF_BOILER_NOMINAL_POWER),
        CONF_PELLET_NOMINAL_ENERGY: config_entry.data.get(CONF_PELLET_NOMINAL_ENERGY),
    }

    # HACK remove hardcoded sensor names
    # TODO we need to somehow recover the last boiler_run_time, energy_output and pellet_consumption sensor values
    # They should be fed to the KWBHeater constructor (?)
    last_boiler_run_time = float(hass.states.get('sensor.easyfire_1_kwb_boiler_run_time').state)
    last_energy_output = float(hass.states.get('sensor.easyfire_1_kwb_energy_output').state)
    last_pellet_consumption = float(hass.states.get('sensor.easyfire_1_kwb_pellet_consumption').state)
    last_timestamp = float(hass.states.get('sensor.easyfire_1_kwb_last_timestamp').state)

    # Async construct inverter object
    # Make sure we can connect to the inverter
    is_success, heater_or_exception = await hass.async_add_executor_job(
        connect_heater(config_heater)
    )
    if not is_success:
        logger.error("Failed to connect to heater", exc_info=heater_or_exception)
        return

    # Configure DataUpdateCoordinator
    async def data_update_method():
        return await hass.async_add_executor_job(data_updater(heater_or_exception))

    # Create a data update coordinator
    coordinator = DataUpdateCoordinator(
        hass,
        logger,
        name=DOMAIN,
        update_method=data_update_method,
        update_interval=max(
            timedelta(seconds=config_entry.data.get(CONF_SCAN_INTERVAL, 5)),
            MIN_TIME_BETWEEN_UPDATES,
        ),
    )
    # and fetch data (at least) once via DataUpdateCoordinator
    await coordinator.async_refresh()

    # Register our inverter device
    device_registry.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, unique_device_id)},
        manufacturer="KWB",
        name=f"KWB {config_entry.data.get(CONF_MODEL)}",
        model=config_entry.data.get(CONF_MODEL),
    )

    # Register our sensor entities
    entities = []
    for description in sensor_descriptions(
        unique_device_id, config_entry.data.get(CONF_MODEL)
    ):
        # Add in the owning device's unique id
        description.device_model = config_entry.data.get(CONF_MODEL)
        # Build sensor name
        entities.append(KWBSensorEntity(coordinator, description))
    async_add_entities(entities, update_before_add=True)
