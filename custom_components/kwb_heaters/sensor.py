"""Support for KWB Easyfire."""
from __future__ import annotations

from dataclasses import dataclass
import logging
import time

from pykwb.kwb import load_signal_maps
import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    RestoreSensor,
    SensorEntity,
    SensorEntityDescription,
    SensorExtraStoredData,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICE,
    CONF_HOST,
    CONF_MODEL,
    CONF_NAME,
    CONF_PORT,
    CONF_TYPE,
    CONF_UNIQUE_ID,
)
from homeassistant.core import HomeAssistant, State
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN

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


class KWBSensorEntity(RestoreSensor):
    """Representation of a KWB Easyfire sensor."""

    # def __init__(self, easyfire, sensor, client_name):
    #     """Initialize the KWB sensor."""
    #     self._easyfire = easyfire
    #     self._sensor = sensor
    #     self._client_name = client_name
    #     self._name = self._sensor.name

    # @property
    # def name(self):
    #     """Return the name."""
    #     return f"{self._client_name} {self._name}"

    # @property
    # def available(self) -> bool:
    #     """Return if sensor is available."""
    #     return self._sensor.available

    # @property
    # def native_value(self):
    #     """Return the state of value."""
    #     if self._sensor.value is not None and self._sensor.available:
    #         return self._sensor.value
    #     return None

    # @property
    # def native_unit_of_measurement(self):
    #     """Return the unit of measurement of this entity, if any."""
    #     return self._sensor.unit_of_measurement

    # async def async_added_to_hass(self) -> None:
    #     """Recover last state"""
    #     state: SensorExtraStoredData | None = await self.async_get_last_sensor_data()
    #     logger.error(
    #         "State for %s is %s %s",
    #         self._name,
    #         state.native_value,
    #         state.native_unit_of_measurement,
    #     )
    #     if not state:
    #         return

    #     self._sensor.value = state.native_value

    #     self.async_schedule_update_ha_state(True)


class KWBSensorCoordinatorEntity(CoordinatorEntity, KWBSensorEntity):
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

    async def async_added_to_hass(self) -> None:
        # No sensor value recovery needed
        pass


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
            # TODO signal_key is a key, not a name. Translate it
            sensor_name = f"{model} {unique_device_id} {signal_key}"

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

    yield KWBSensorEntityDescription(
        key="boiler_nominal_power",
        translation_key="boiler_nominal_power",
        name=f"{model} {unique_device_id} Boiler Nominal Power",
        native_unit_of_measurement="kw",
        device_class="power",
        state_class=state_class,
        device_id=unique_device_id,
        device_model=model,
    )
    yield KWBSensorEntityDescription(
        key="boiler_run_time",
        translation_key="boiler_run_time",
        name=f"{model} {unique_device_id} Boiler Run Time",
        native_unit_of_measurement="sec",
        device_class="duration",
        state_class=state_class,
        device_id=unique_device_id,
        device_model=model,
    )
    yield KWBSensorEntityDescription(
        key="energy_output",
        translation_key="energy_output",
        name=f"{model} {unique_device_id} Energy Output",
        native_unit_of_measurement="kwH",
        device_class="power",
        state_class=state_class,
        device_id=unique_device_id,
        device_model=model,
    )
    yield KWBSensorEntityDescription(
        key="pellet_consumption",
        translation_key="pellet_consumption",
        name=f"{model} {unique_device_id} Pellet Consumption",
        native_unit_of_measurement="kg",
        device_class="weight",
        state_class=state_class,
        device_id=unique_device_id,
        device_model=model,
    )
    yield KWBSensorEntityDescription(
        key="pellet_consumption",
        translation_key="pellet_consumption",
        name=f"{model} {unique_device_id} Pellet Consumption",
        native_unit_of_measurement="kg",
        device_class="weight",
        state_class=state_class,
        device_id=unique_device_id,
        device_model=model,
    )
    yield KWBSensorEntityDescription(
        key="last_timestamp",
        translation_key="last_timestamp",
        name=f"{model} {unique_device_id} Last Timestamp",
        native_unit_of_measurement="msec",
        device_class="duration",
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
    # Retrieve data update coordinator
    coordinator = hass.data[DOMAIN][config_entry.entry_id].get("coordinator")

    # Register our sensor entities
    entities = []
    for description in sensor_descriptions(
        unique_device_id=config_entry.data.get(CONF_UNIQUE_ID),
        model=config_entry.data.get(CONF_MODEL),
    ):
        # Add in the owning device's unique id
        # description.device_model = config_entry.data.get(CONF_MODEL)
        # Build sensor name
        entities.append(KWBSensorCoordinatorEntity(coordinator, description))

    async_add_entities(entities, update_before_add=True)
