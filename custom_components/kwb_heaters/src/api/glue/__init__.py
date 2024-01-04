"""The KWB integration"""

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_MODEL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

logger = logging.getLogger(__name__)

DOMAIN: str = ...
MANUFACTURER: str = ...
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
DEVICE_ID_FROM_CONFIG = True


# Configure DataUpdateCoordinator update method
async def f_data_update_method(hass: HomeAssistant, appliance: Appliance):
    return await hass.async_add_executor_job(data_updater(appliance))


async def f_config_entry_to_appliance(config_entry: ConfigEntry) -> Appliance:
    ...


async def f_appliance_to_devices(appliance: Appliance) -> Device[]:
    ...


async def f_unique_device_id_from_config_entry(config_entry: ConfigEntry) -> str:
    ...


async def f_unique_device_id_from_device(device: Device) -> str:
    ...


async def f_test_connection_to_appliance(appliance: Appliance)-> bool:
    ...


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Entry point to set up KWB heaters"""

    appliance: Appliance = f_config_entry_to_appliance(config_entry)

    # Async construct heater object
    # Make sure we can connect to the heater
    is_success = await hass.async_add_executor_job(
        f_test_connection_to_appliance(appliance)
    )
    if not is_success:
        logger.error("Failed to connect to heater")
        return

    # TODO move this to __init__.py
    # Create a data update coordinator
    coordinator = DataUpdateCoordinator(
        hass,
        logger,
        name=DOMAIN,
        update_method=f_data_update_method,
        update_interval=max(
            timedelta(seconds=config_entry.data.get(CONF_SCAN_INTERVAL, 5)),
            MIN_TIME_BETWEEN_UPDATES,
        ),
    )
    # and fetch data (at least) once via DataUpdateCoordinator
    # ConfigEntryNotReady will be raised here on failure and HomeAssistant will
    # continue trying to connect in the background.
    await coordinator.async_config_entry_first_refresh()

    # Configure devices for our appliance
    devices: Device[] = f_appliance_to_devices(appliance)
    for device in devices:
        # At this point, it should be possible that an appliance has many devices
        # TODO Figure out the unique device id for each device
        unique_device_id: str = (
            f_unique_device_id_from_config_entry(config_entry)
            if DEVICE_ID_FROM_CONFIG
            else f_unique_device_id_from_device(device)
        )

    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = {
        "coordinator": coordinator,
        "appliance": appliance,
    }

    # Register our inverter device
    device_registry.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, unique_device_id)},
        manufacturer=MANUFACTURER,
        name=f"{MANUFACTURER} {config_entry.data.get(CONF_MODEL)}",
        model=config_entry.data.get(CONF_MODEL),
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
