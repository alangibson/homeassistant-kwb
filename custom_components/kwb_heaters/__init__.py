"""The KWB integration"""

from datetime import timedelta
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_MODEL,
    CONF_PORT,
    CONF_PROTOCOL,
    CONF_TIMEOUT,
    CONF_UNIQUE_ID,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .config_flow import options_update_listener
from .const import (
    CONF_BOILER_EFFICIENCY,
    CONF_BOILER_NOMINAL_POWER,
    CONF_PELLET_NOMINAL_ENERGY,
    DOMAIN,
    OPT_LAST_BOILER_RUN_TIME,
    OPT_LAST_ENERGY_OUTPUT,
    OPT_LAST_PELLET_CONSUMPTION,
    OPT_LAST_TIMESTAMP,
)
from .coordinator import data_updater
from .src.impl.appliance import connect_appliance

logger = logging.getLogger(__name__)


PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
SCAN_INTERVAL_SEC = 10

# HomeAssistant reads this for entities with async_update() (?)
SCAN_INTERVAL = timedelta(seconds=SCAN_INTERVAL_SEC)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> True:
    """Entry point to set up KWB heaters"""

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
        CONF_TIMEOUT: int(config_entry.data.get(CONF_TIMEOUT, 2)),
        CONF_MODEL: config_entry.data.get(CONF_MODEL),
        CONF_PROTOCOL: config_entry.data.get(CONF_PROTOCOL),
        CONF_BOILER_EFFICIENCY: config_entry.data.get(CONF_BOILER_EFFICIENCY),
        CONF_BOILER_NOMINAL_POWER: config_entry.data.get(CONF_BOILER_NOMINAL_POWER),
        CONF_PELLET_NOMINAL_ENERGY: config_entry.data.get(CONF_PELLET_NOMINAL_ENERGY),
    }
    # HACK remove hardcoded sensor names
    # TODO we need to somehow recover the last boiler_run_time, energy_output and pellet_consumption sensor values
    # They should be fed to the KWBHeater constructor (?)
    # FIXME these sensors need to be prefixed with {model}_{unique_id}_
    sensor_boiler_run_time = hass.states.get("sensor.boiler_run_time")
    sensor_energy_output = hass.states.get("sensor.energy_output")
    sensor_pellet_consumption = hass.states.get("sensor.pellet_consumption")
    sensor_last_timestamp = hass.states.get("sensor.last_timestamp")
    last_boiler_run_time = (
        float(sensor_boiler_run_time.state) if sensor_boiler_run_time else 0.0
    )
    last_energy_output = (
        float(sensor_energy_output.state) if sensor_energy_output else 0.0
    )
    last_pellet_consumption = (
        float(sensor_pellet_consumption.state) if sensor_pellet_consumption else 0.0
    )
    last_timestamp = (
        float(sensor_last_timestamp.state)
        if sensor_last_timestamp
        else time.time_ns() / 1000000
    )
    config_heater.update(
        {
            OPT_LAST_TIMESTAMP: last_timestamp,
            OPT_LAST_BOILER_RUN_TIME: last_boiler_run_time,
            OPT_LAST_ENERGY_OUTPUT: last_energy_output,
            OPT_LAST_PELLET_CONSUMPTION: last_pellet_consumption,
        }
    )

    # Async construct heater object
    # Make sure we can connect to the heater
    is_success, heater_or_exception = await hass.async_add_executor_job(
        connect_appliance(config_heater)
    )
    if not is_success:
        logger.error("Failed to connect to heater", exc_info=heater_or_exception)
        # return False
        raise ConfigEntryNotReady("Failed to connect to heater")

    # Configure DataUpdateCoordinator
    async def data_update_method():
        # return await hass.async_add_executor_job(data_updater(heater_or_exception))
        return data_updater(heater_or_exception)()

    # TODO move this to __init__.py
    # Create a data update coordinator
    coordinator = DataUpdateCoordinator(
        hass,
        logger,
        name=DOMAIN,
        update_method=data_update_method,
        update_interval=SCAN_INTERVAL,
    )
    # and fetch data (at least) once via DataUpdateCoordinator
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = {
        "coordinator": coordinator,
        "device": heater_or_exception,
    }

    # We can't add CONF_UNIQUE_ID here or we get an error in the device registry
    device_info: device_registry.DeviceInfo = {
        "identifiers": {(DOMAIN, unique_device_id)},
        "manufacturer": "KWB",
        "name": f"KWB {config_entry.data.get(CONF_MODEL)}",
        "model": config_entry.data.get(CONF_MODEL),
    }

    # Register our inverter device
    device_entry: device_registry.DeviceEntry = device_registry.async_get(
        hass
    ).async_get_or_create(
        config_entry_id=config_entry.entry_id,
        # identifiers={(DOMAIN, unique_device_id)},
        # manufacturer="KWB",
        # name=f"KWB {config_entry.data.get(CONF_MODEL)}",
        # model=config_entry.data.get(CONF_MODEL),
        **device_info,
    )

    # Register options update handler
    # hass_data = dict(config_entry.data)
    # Registers update listener to update config entry when options are updated.
    # unsub_options_update_listener = config_entry.add_update_listener(options_update_listener)
    # Store a reference to the unsubscribe function to cleanup if an entry is unloaded.
    # hass_data["unsub_options_update_listener"] = unsub_options_update_listener
    # hass.data[DOMAIN][config_entry.entry_id] = hass_data
    config_entry.add_update_listener(options_update_listener)

    # Forward the setup to the sensor platform.
    # hass.async_create_task(
    #     # For platform 'sensor', file sensor.py must exist
    #     hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    # )

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    return True


# TODO Unload gracefully
# https://github.com/home-assistant/core/blob/dev/homeassistant/components/fronius/__init__.py
# async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
#   ...
