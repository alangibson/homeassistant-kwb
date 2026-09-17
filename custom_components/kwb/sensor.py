"""Support for KWB Easyfire."""

from datetime import timedelta
from typing import override

import voluptuous as vol
from homeassistant.components.integration.const import METHOD_LEFT
from homeassistant.components.integration.sensor import IntegrationSensor
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA as SENSOR_PLATFORM_SCHEMA,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_DEVICE,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_TYPE,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import discovery
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from pykwb import kwb

from . import KWBConfigEntry
from .client import create_client
from .const import CONF_NOMINAL_POWER, CONF_RAW, DEFAULT_NAME, DEFAULT_RAW, DOMAIN
from .entity import KWBEntity

MODE_SERIAL = 0
MODE_TCP = 1

# Older released pykwb versions do not define pressure or duration types.
DEVICE_CLASSES = {
    getattr(kwb, sensor_type): device_class
    for sensor_type, device_class in (
        ("PROP_SENSOR_TEMPERATURE", SensorDeviceClass.TEMPERATURE),
        ("PROP_SENSOR_PRESSURE", SensorDeviceClass.PRESSURE),
        ("PROP_SENSOR_DURATION", SensorDeviceClass.DURATION),
    )
    if hasattr(kwb, sensor_type)
}
# PROP_SENSOR_SPEED is rotational speed (rpm), unsupported by HA's SPEED class.

SERIAL_SCHEMA = SENSOR_PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_RAW, default=DEFAULT_RAW): cv.boolean,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_DEVICE): cv.string,
        vol.Required(CONF_TYPE): "serial",
    }
)

ETHERNET_SCHEMA = SENSOR_PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_RAW, default=DEFAULT_RAW): cv.boolean,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT): cv.port,
        vol.Required(CONF_TYPE): "tcp",
    }
)

PLATFORM_SCHEMA = vol.Schema(vol.Any(SERIAL_SCHEMA, ETHERNET_SCHEMA))


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the KWB component."""
    raw = config.get(CONF_RAW)
    client_name = config.get(CONF_NAME, DEFAULT_NAME)
    easyfire = await hass.async_add_executor_job(create_client, config)
    easyfire.async_start(hass)

    async def async_stop(event: Event) -> None:
        await easyfire.async_stop(hass)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_stop)

    add_entities(
        KWBSensor(easyfire, sensor, client_name)
        for sensor in easyfire.get_sensors()
        if sensor.sensor_type != kwb.PROP_SENSOR_FLAG
        and (sensor.sensor_type != kwb.PROP_SENSOR_RAW or raw)
    )

    await discovery.async_load_platform(
        hass,
        Platform.BINARY_SENSOR,
        DOMAIN,
        {"client": easyfire, CONF_NAME: client_name},
        config,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KWBConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add every decoded pykwb sensor for a UI-configured heater."""
    client = entry.runtime_data
    nominal_power = entry.data.get(CONF_NOMINAL_POWER)
    async_add_entities(
        KWBSensor(client, sensor, entry.data[CONF_NAME], entry.entry_id)
        for sensor in client.get_sensors()
        if sensor.sensor_type != kwb.PROP_SENSOR_FLAG
        and (nominal_power is None or sensor.name != "Heater Power Output")
        and (
            sensor.sensor_type != kwb.PROP_SENSOR_RAW
            or entry.data.get(CONF_RAW, DEFAULT_RAW)
        )
    )

    if nominal_power is not None:
        for sensor in client.get_sensors():
            if sensor.name != "Heater Output":
                continue
            power = KWBPowerOutputSensor(
                client, sensor, entry.data[CONF_NAME], entry.entry_id, nominal_power
            )
            # Resolve the registered ID, including user renames and name collisions,
            # before the energy sensor starts listening for power state changes.
            source = er.async_get(hass).async_get_or_create(
                Platform.SENSOR,
                DOMAIN,
                f"{entry.entry_id}_Heater Power Output",
                suggested_object_id=power.name,
                config_entry=entry,
            )
            async_add_entities(
                [
                    power,
                    KWBEnergyOutputSensor(
                        power, source.entity_id, entry.entry_id, entry.data[CONF_NAME]
                    ),
                ]
            )


class KWBSensor(KWBEntity, SensorEntity):
    """Representation of a KWB Easyfire numeric or raw sensor."""

    @property
    @override
    def device_class(self) -> SensorDeviceClass | None:
        """Return the HA measurement class for this pykwb type."""
        return DEVICE_CLASSES.get(self._sensor.sensor_type)

    @property
    @override
    def native_value(self):
        """Return the state of value."""
        if self._sensor.value is not None and self._sensor.available:
            return self._sensor.value
        return None

    @property
    @override
    def native_unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        unit = self._sensor.unit_of_measurement
        if self.device_class == SensorDeviceClass.DURATION:
            return {
                "msec": UnitOfTime.MILLISECONDS,
                "sec": UnitOfTime.SECONDS,
            }.get(unit, unit)
        return unit


class KWBPowerOutputSensor(KWBEntity, SensorEntity):
    """Power calculated from the heater's nominal rating and output percentage."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(
        self,
        easyfire: kwb.KWBEasyfire,
        sensor: kwb.KWBEasyfireSensor,
        client_name: str,
        entry_id: str,
        nominal_power: float,
    ) -> None:
        super().__init__(easyfire, sensor, client_name, entry_id)
        self._name = "Heater Power Output"
        self._attr_unique_id = f"{entry_id}_Heater Power Output"
        self._nominal_power = nominal_power

    @property
    @override
    def native_value(self) -> float | None:
        """Return current power in kW, or unknown without a valid reading."""
        if self._sensor.available and self._sensor.value is not None:
            return self._nominal_power * (self._sensor.value / 100)
        return None


class KWBEnergyOutputSensor(IntegrationSensor):
    """Accumulate heater power using Home Assistant's restorable integral sensor."""

    def __init__(
        self,
        power: KWBPowerOutputSensor,
        source_entity: str,
        entry_id: str,
        client_name: str,
    ) -> None:
        super().__init__(
            integration_method=METHOD_LEFT,
            name=f"{client_name} Heater Energy Output",
            round_digits=3,
            source_entity=source_entity,
            unique_id=f"{entry_id}_Heater Energy Output",
            unit_prefix=None,  # The source already reports kW.
            unit_time=UnitOfTime.HOURS,
            max_sub_interval=timedelta(minutes=1),
        )
        self._attr_device_info = power.device_info
