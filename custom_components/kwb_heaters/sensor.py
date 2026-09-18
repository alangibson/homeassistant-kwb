"""Support for KWB Heaters"""

from datetime import timedelta
from decimal import Decimal
from math import isfinite
from typing import override

import voluptuous as vol
from homeassistant.components.integration.const import METHOD_LEFT
from homeassistant.components.integration.sensor import (
    IntegrationSensor,
    IntegrationSensorExtraStoredData,
)
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA as SENSOR_PLATFORM_SCHEMA,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorExtraStoredData,
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
    UnitOfMass,
    UnitOfPower,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import discovery
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import dt as dt_util
from pykwb import kwb

from . import KWBConfigEntry
from .client import create_client
from .const import (
    CONF_BOILER_EFFICIENCY,
    CONF_NOMINAL_POWER,
    CONF_PELLET_BULK_DENSITY,
    CONF_PELLET_ENERGY,
    CONF_PELLET_PRICE,
    CONF_RAW,
    DEFAULT_NAME,
    DEFAULT_PELLET_BULK_DENSITY,
    DEFAULT_PELLET_PRICE,
    DEFAULT_RAW,
    DOMAIN,
)
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
    heater = await hass.async_add_executor_job(create_client, config)
    heater.async_start(hass)

    async def async_stop(event: Event) -> None:
        await heater.async_stop(hass)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_stop)

    add_entities(
        KWBSensor(heater, sensor, client_name)
        for sensor in heater.get_sensors()
        if sensor.sensor_type != kwb.PROP_SENSOR_FLAG
        and (sensor.sensor_type != kwb.PROP_SENSOR_RAW or raw)
    )

    await discovery.async_load_platform(
        hass,
        Platform.BINARY_SENSOR,
        DOMAIN,
        {"client": heater, CONF_NAME: client_name},
        config,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KWBConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add every decoded pykwb sensor for a UI-configured heater."""
    client = entry.runtime_data
    config = {**entry.data, **entry.options}
    nominal_power = config.get(CONF_NOMINAL_POWER)
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
            efficiency = config.get(CONF_BOILER_EFFICIENCY)
            pellet_energy = config.get(CONF_PELLET_ENERGY)
            if efficiency is not None and pellet_energy is not None:
                consumption = KWBPelletConsumptionRateSensor(
                    client,
                    sensor,
                    entry.data[CONF_NAME],
                    entry.entry_id,
                    nominal_power,
                    efficiency,
                    pellet_energy,
                )
                volume = KWBPelletVolumeFlowRateSensor(
                    client,
                    sensor,
                    entry.data[CONF_NAME],
                    entry.entry_id,
                    consumption,
                    config.get(CONF_PELLET_BULK_DENSITY, DEFAULT_PELLET_BULK_DENSITY),
                )
                consumption_source = er.async_get(hass).async_get_or_create(
                    Platform.SENSOR,
                    DOMAIN,
                    f"{entry.entry_id}_Pellet Consumption Rate",
                    suggested_object_id=consumption.name,
                    config_entry=entry,
                )
                total = KWBPelletConsumptionSensor(
                    consumption,
                    consumption_source.entity_id,
                    entry.entry_id,
                    entry.data[CONF_NAME],
                )
                total_source = er.async_get(hass).async_get_or_create(
                    Platform.SENSOR,
                    DOMAIN,
                    f"{entry.entry_id}_Pellet Consumption",
                    suggested_object_id=total.name,
                    config_entry=entry,
                )
                async_add_entities(
                    [
                        consumption,
                        volume,
                        total,
                        KWBPelletConsumptionCostSensor(
                            entry, total, total_source.entity_id, hass.config.currency
                        ),
                    ]
                )

            @callback
            def update_properties() -> None:
                updated = {**entry.data, **entry.options}
                power._nominal_power = updated[CONF_NOMINAL_POWER]
                power.async_write_ha_state()
                if efficiency is not None and pellet_energy is not None:
                    consumption._nominal_power = updated[CONF_NOMINAL_POWER]
                    consumption._efficiency = updated[CONF_BOILER_EFFICIENCY]
                    consumption._pellet_energy = updated[CONF_PELLET_ENERGY]
                    volume._bulk_density = updated.get(
                        CONF_PELLET_BULK_DENSITY, DEFAULT_PELLET_BULK_DENSITY
                    )
                    consumption.async_write_ha_state()
                    volume.async_write_ha_state()

            entry.async_on_unload(
                async_dispatcher_connect(
                    hass, f"{DOMAIN}_{entry.entry_id}_properties", update_properties
                )
            )
            break


class KWBSensor(KWBEntity, SensorEntity):
    """Representation of a KWB Heater numeric or raw sensor."""

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

    _attr_device_class: SensorDeviceClass | None = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement: str = UnitOfPower.KILO_WATT

    def __init__(
        self,
        heater: kwb.KWBEasyfire,
        sensor: kwb.KWBEasyfireSensor,
        client_name: str,
        entry_id: str,
        nominal_power: float,
    ) -> None:
        super().__init__(heater, sensor, client_name, entry_id)
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


class KWBPelletConsumptionRateSensor(KWBPowerOutputSensor):
    """Estimate pellet mass consumption from thermal output and fuel properties."""

    _attr_device_class = None
    _attr_native_unit_of_measurement = "kg/h"
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        heater: kwb.KWBEasyfire,
        sensor: kwb.KWBEasyfireSensor,
        client_name: str,
        entry_id: str,
        nominal_power: float,
        efficiency: float,
        pellet_energy: float,
    ) -> None:
        super().__init__(heater, sensor, client_name, entry_id, nominal_power)
        self._name = "Pellet Consumption Rate"
        self._attr_unique_id = f"{entry_id}_Pellet Consumption Rate"
        self._efficiency = efficiency
        self._pellet_energy = pellet_energy

    @property
    @override
    def native_value(self) -> float | None:
        power = super().native_value
        if (
            power is None
            or not isfinite(power)
            or power < 0
            or not 0 < self._efficiency <= 100
            or not isfinite(self._pellet_energy)
            or self._pellet_energy <= 0
        ):
            return None
        denominator = (self._efficiency / 100) * self._pellet_energy
        if denominator == 0:
            return None
        rate = power / denominator
        return rate if isfinite(rate) else None


class KWBPelletVolumeFlowRateSensor(KWBEntity, SensorEntity):
    """Estimate the bulk volume of pellets consumed per hour."""

    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_HOUR
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        heater: kwb.KWBEasyfire,
        sensor: kwb.KWBEasyfireSensor,
        client_name: str,
        entry_id: str,
        consumption: KWBPelletConsumptionRateSensor,
        bulk_density: float,
    ) -> None:
        super().__init__(heater, sensor, client_name, entry_id)
        self._name = "Pellet Volume Flow Rate"
        self._attr_unique_id = f"{entry_id}_Pellet Volume Flow Rate"
        self._consumption = consumption
        self._bulk_density = bulk_density

    @property
    @override
    def native_value(self) -> float | None:
        rate = self._consumption.native_value
        if rate is None or not isfinite(self._bulk_density) or self._bulk_density <= 0:
            return None
        volume = rate / self._bulk_density
        return volume if isfinite(volume) else None


class KWBResettableIntegrationSensor(IntegrationSensor):
    """Share reset boundaries and zero restoration for accumulated totals."""

    _entry_id: str
    _reset_target_key: str

    @override
    async def async_added_to_hass(self) -> None:
        """Restore the reset marker and register the target for the reset button."""
        if (state := await self.async_get_last_state()) is not None:
            if last_reset := state.attributes.get("last_reset"):
                self._attr_last_reset = dt_util.parse_datetime(last_reset)
        await super().async_added_to_hass()
        self._last_integration_time = dt_util.utcnow()
        self._last_integration_trigger = type(
            self._last_integration_trigger
        ).TimeElapsed
        targets = self.hass.data.setdefault(DOMAIN, {}).setdefault(
            self._reset_target_key, {}
        )
        targets[self._entry_id] = self
        self.async_on_remove(lambda: targets.pop(self._entry_id, None))

    @override
    async def async_get_last_sensor_data(
        self,
    ) -> IntegrationSensorExtraStoredData | None:
        """Also restore a zero total, which the upstream truthiness check drops."""
        restored = await super().async_get_last_sensor_data()
        if restored is not None:
            return restored
        if (extra := await self.async_get_last_extra_data()) is not None:
            data = SensorExtraStoredData.from_dict(extra.as_dict())
            if data is not None and data.native_value == 0:
                return IntegrationSensorExtraStoredData(
                    Decimal(0),
                    data.native_unit_of_measurement,
                    self._source_entity,
                    Decimal(0),
                )
        return None

    @callback
    def async_reset(self) -> None:
        """Begin a new statistics cycle and integrate only time after this reset."""
        now = dt_util.utcnow()
        self._cancel_max_sub_interval_exceeded_callback()
        self._state = self._last_valid_state = Decimal(0)
        if self.state_class == SensorStateClass.TOTAL:
            self._attr_last_reset = now
        self._last_integration_time = now
        # Treat reset as a timer boundary: the next source event must not integrate
        # from its previous report, which may precede the reset.
        self._last_integration_trigger = type(
            self._last_integration_trigger
        ).TimeElapsed
        self._schedule_max_sub_interval_exceeded_if_state_is_numeric(
            self.hass.states.get(self._source_entity)
        )
        self.async_write_ha_state()


class KWBPelletConsumptionSensor(KWBResettableIntegrationSensor):
    """Accumulate estimated pellet mass without resetting on boiler restarts."""

    _reset_target_key = "pellet_reset_targets"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        consumption: KWBPelletConsumptionRateSensor,
        source_entity: str,
        entry_id: str,
        client_name: str,
    ) -> None:
        super().__init__(
            integration_method=METHOD_LEFT,
            name=f"{client_name} Pellet Consumption",
            round_digits=6,
            source_entity=source_entity,
            unique_id=f"{entry_id}_Pellet Consumption",
            unit_prefix=None,
            unit_time=UnitOfTime.HOURS,
            max_sub_interval=timedelta(minutes=1),
        )
        self._attr_suggested_display_precision = 2
        self._attr_device_info = consumption.device_info
        self._entry_id = entry_id

    @property
    @override
    def device_class(self) -> SensorDeviceClass:
        """Mass cannot be inferred from the source's custom kg/h unit."""
        return SensorDeviceClass.WEIGHT

    @property
    @override
    def native_unit_of_measurement(self) -> str:
        return UnitOfMass.KILOGRAMS

    @property
    @override
    def native_value(self) -> Decimal:
        """Start at zero until the first valid interval has accumulated."""
        value = super().native_value
        return value if value is not None else Decimal(0)


class KWBEnergyOutputSensor(KWBResettableIntegrationSensor):
    """Accumulate heater power using Home Assistant's restorable integral sensor."""

    _reset_target_key = "energy_reset_targets"

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
        self._entry_id = entry_id


class KWBPelletConsumptionCostSensor(SensorEntity):
    """Value the accumulated pellet mass at the currently configured price."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_should_poll = False
    _attr_suggested_display_precision = 2
    # Repricing the entire total is not incremental expenditure, so omit state_class.

    def __init__(
        self,
        entry: KWBConfigEntry,
        consumption: KWBPelletConsumptionSensor,
        source_entity: str,
        currency: str,
    ) -> None:
        self._entry = entry
        self._consumption = consumption
        self._source_entity = source_entity
        self._attr_name = f"{entry.data[CONF_NAME]} Pellet Consumption Cost"
        self._attr_unique_id = f"{entry.entry_id}_Pellet Consumption Cost"
        self._attr_device_info = consumption.device_info
        self._attr_native_unit_of_measurement = currency

    @property
    @override
    def available(self) -> bool:
        return self._consumption.available

    @property
    @override
    def native_value(self) -> Decimal | None:
        if not self.available:
            return None
        price = self._entry.options.get(
            CONF_PELLET_PRICE,
            self._entry.data.get(CONF_PELLET_PRICE, DEFAULT_PELLET_PRICE),
        )
        return self._consumption.native_value / Decimal(1000) * Decimal(str(price))

    @override
    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def update_from_source(event: Event[EventStateChangedData]) -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_entity, update_from_source
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_{self._entry.entry_id}_properties",
                self.async_write_ha_state,
            )
        )
