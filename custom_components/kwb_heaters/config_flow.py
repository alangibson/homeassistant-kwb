"""KWB Heater config flow."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    FlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_MODEL,
    CONF_PORT,
    CONF_PROTOCOL,
    CONF_SENDER,
    CONF_TIMEOUT,
    CONF_UNIQUE_ID,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_registry import (
    RegistryEntry,
    async_entries_for_config_entry,
    async_get,
)
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    selector,
)

from .const import (
    CONF_BOILER_EFFICIENCY,
    CONF_BOILER_NOMINAL_POWER,
    CONF_PELLET_NOMINAL_ENERGY,
    DEFAULT_NAME,
    DOMAIN,
    OPT_LAST_BOILER_RUN_TIME,
    OPT_LAST_ENERGY_OUTPUT,
    OPT_LAST_PELLET_CONSUMPTION,
    OPT_LAST_TIMESTAMP,
)
from .heater import connect_heater

logger = logging.getLogger(__name__)


# This is the schema that used to display the UI to the user.
def data_schema(defaults: dict):
    # Load up existing options/config values
    conf_unique_id = defaults.get(CONF_UNIQUE_ID)
    conf_host = defaults.get(CONF_HOST)
    conf_model = defaults.get(CONF_MODEL, "easyfire_1")
    conf_port = defaults.get(CONF_PORT, "8899")
    conf_protocol = defaults.get(CONF_PROTOCOL, "tcp")
    conf_sender = defaults.get(CONF_SENDER, "comfort_3")
    conf_timeout = defaults.get(CONF_TIMEOUT, 2)
    conf_boiler_efficiency = defaults.get(CONF_BOILER_EFFICIENCY, 90.0)
    conf_boiler_nominal_power = defaults.get(CONF_BOILER_NOMINAL_POWER)
    conf_pellet_nominal_energy = defaults.get(CONF_PELLET_NOMINAL_ENERGY)
    # Load up existing sensor values
    sensor_boiler_run_time = defaults.get("boiler_run_time")
    sensor_energy_output = defaults.get("energy_output")
    sensor_pellet_consumption = defaults.get("pellet_consumption")
    sensor_last_timestamp = defaults.get("last_timestamp")

    last_boiler_run_time = (
        float(sensor_boiler_run_time) if sensor_boiler_run_time else None
    )
    last_energy_output = float(sensor_energy_output) if sensor_energy_output else None
    last_pellet_consumption = (
        float(sensor_pellet_consumption) if sensor_pellet_consumption else None
    )
    last_timestamp = (
        float(sensor_last_timestamp)
        if sensor_last_timestamp
        # else time.time_ns() / 1000000
        else None
    )

    schema = vol.Schema(
        {
            vol.Required(CONF_UNIQUE_ID, default=conf_unique_id): str,
            vol.Required(CONF_MODEL, default=conf_model): SelectSelector(
                SelectSelectorConfig(options=["easyfire_1"], translation_key=CONF_MODEL)
            ),
            vol.Required(CONF_SENDER, default=conf_sender): SelectSelector(
                SelectSelectorConfig(options=["comfort_3"], translation_key=CONF_SENDER)
            ),
            vol.Required(CONF_PROTOCOL, default=conf_protocol): SelectSelector(
                SelectSelectorConfig(options=["tcp"], translation_key=CONF_PROTOCOL)
            ),
            vol.Required(CONF_HOST, default=conf_host): str,
            vol.Required(CONF_PORT, default=conf_port): int,
            vol.Required(CONF_TIMEOUT, default=conf_timeout): int,
            vol.Optional(CONF_BOILER_EFFICIENCY, default=conf_boiler_efficiency): float,
            vol.Optional(
                CONF_BOILER_NOMINAL_POWER, default=conf_boiler_nominal_power
            ): float,
            vol.Optional(
                CONF_PELLET_NOMINAL_ENERGY, default=conf_pellet_nominal_energy
            ): float,
            # vol.Optional(OPT_LAST_BOILER_RUN_TIME, default=last_boiler_run_time): float,
            # vol.Optional(OPT_LAST_ENERGY_OUTPUT, default=last_energy_output): float,
            # vol.Optional(
            #     OPT_LAST_PELLET_CONSUMPTION, default=last_pellet_consumption
            # ): float,
            # vol.Optional(OPT_LAST_TIMESTAMP, default=last_timestamp): float,
        }
    )

    return schema


class KWBConfigFlow(ConfigFlow, domain=DOMAIN):
    """KWB config flow."""

    VERSION = 1

    async def validate_input(
        self, hass: HomeAssistant, user_input: dict = None
    ) -> dict[str, Any]:
        """Validate that the user input allows us to connect to the heater.
        Data has the keys from DATA_SCHEMA with values provided by the user.
        """

        # Accumulate validation errors. Key is name of field from DATA_SCHEMA
        errors = {}

        # Don't do anything if we don't have a configuration
        if not user_input:
            return None

        # Validate the data can be used to set up a connection.
        is_success, heater = await hass.async_add_executor_job(
            connect_heater(user_input)
        )
        # If we can't connect, set a value indicating this so we can tell the user
        if not is_success:
            errors["base"] = "cannot_connect"

        return (errors, heater)

    async def async_step_user(self, user_input=None):
        """Initial configuration step.

        Either show config data entry form to the user, or create a config entry.
        """
        # Either show modal form, or create config entry then move on
        if not user_input:  # Just show the modal form and return if no user input
            return self.async_show_form(step_id="user", data_schema=data_schema({}))
        else:
            # We got user input, so do something with it

            # Validate inputs and do a test connection/scrape of the heater
            # Both info and errors are None when config flow is first invoked
            errors, heater = await self.validate_input(self.hass, user_input)

            # Either display errors in form, or create config entry and close form
            if not errors or not len(errors.keys()):
                # Figure out a unique id (that never changes!) for the device
                unique_device_id = user_input.get(CONF_UNIQUE_ID)
                await self.async_set_unique_id(unique_device_id)
                # self._abort_if_unique_id_configured(updates={CONF_HOST: user_input[CONF_HOST]})
                self._abort_if_unique_id_configured()

                # Create the config entry
                return self.async_create_entry(title=DEFAULT_NAME, data=user_input)
            else:
                # If there is no user input or there were errors, show the form again,
                # including any errors that were found with the input.
                return self.async_show_form(
                    step_id="user", data_schema=data_schema(user_input), errors=errors
                )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return KWBOptionsFlow(config_entry)


class KWBOptionsFlow(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""

        # Grab all configured repos from the entity registry so we can populate the
        # multi-select dropdown that will allow a user to remove a repo.
        # entity_registry: RegistryEntry = await async_get(self.hass)
        # entries: list[RegistryEntry] = async_entries_for_config_entry(
        #     entity_registry, self.config_entry.entry_id
        # )
        # TODO unpack config values
        # Default value for our multi-select.
        # all_repos = {e.entity_id: e.original_name for e in entries}
        # repo_map = {e.entity_id: e for e in entries}

        # TODO Load up existing options/config values
        # conf_unique_id = self.config_entry.data.get(CONF_UNIQUE_ID)
        # conf_host = self.config_entry.data.get(CONF_HOST)
        # conf_model = self.config_entry.data.get(CONF_MODEL)
        # conf_port = self.config_entry.data.get(CONF_PORT)
        # conf_protocol = self.config_entry.data.get(CONF_PROTOCOL)
        # conf_sender = self.config_entry.data.get(CONF_SENDER)
        # conf_timeout = self.config_entry.data.get(CONF_TIMEOUT)
        # conf_boiler_efficiency = self.config_entry.data.get(
        #     CONF_BOILER_EFFICIENCY, 90.0
        # )
        # conf_boiler_nominal_power = self.config_entry.data.get(
        #     CONF_BOILER_NOMINAL_POWER
        # )
        # conf_pellet_nominal_energy = self.config_entry.data.get(
        #     CONF_PELLET_NOMINAL_ENERGY
        # )
        # # logger.error(conf_host, conf_model, conf_port, conf_protocol, conf_sender, conf_timeout)
        # # logger.error(conf_boiler_efficiency, conf_boiler_nominal_power, conf_pellet_nominal_energy)

        # # Load up existing sensor values
        # # FIXME these sensors need to be prefixed with {model}_{unique_id}_
        # sensor_boiler_run_time = self.hass.states.get("sensor.boiler_run_time")
        # sensor_energy_output = self.hass.states.get("sensor.energy_output")
        # sensor_pellet_consumption = self.hass.states.get("sensor.pellet_consumption")
        # sensor_last_timestamp = self.hass.states.get("sensor.last_timestamp")
        # last_boiler_run_time = (
        #     float(sensor_boiler_run_time.state) if sensor_boiler_run_time else 0.0
        # )
        # last_energy_output = (
        #     float(sensor_energy_output.state) if sensor_energy_output else 0.0
        # )
        # last_pellet_consumption = (
        #     float(sensor_pellet_consumption.state) if sensor_pellet_consumption else 0.0
        # )
        # last_timestamp = (
        #     float(sensor_last_timestamp.state)
        #     if sensor_last_timestamp
        #     else time.time_ns() / 1000000
        # )
        # # logger.error(last_boiler_run_time, last_energy_output, last_pellet_consumption, last_timestamp)

        # schema = vol.Schema(
        #     {
        #         vol.Required(CONF_UNIQUE_ID, default=conf_unique_id): str,
        #         vol.Required(CONF_MODEL, default=conf_model): SelectSelector(
        #             SelectSelectorConfig(
        #                 options=["easyfire_1"], translation_key=CONF_MODEL
        #             )
        #         ),
        #         vol.Required(CONF_SENDER, default=conf_sender): SelectSelector(
        #             SelectSelectorConfig(
        #                 options=["comfort_3"], translation_key=CONF_SENDER
        #             )
        #         ),
        #         vol.Required(CONF_PROTOCOL, default=conf_protocol): SelectSelector(
        #             SelectSelectorConfig(options=["tcp"], translation_key=CONF_PROTOCOL)
        #         ),
        #         vol.Required(CONF_HOST, default=conf_host): str,
        #         vol.Required(CONF_PORT, default=conf_port): int,
        #         vol.Required(CONF_TIMEOUT, default=conf_timeout): int,
        #         vol.Optional(
        #             CONF_BOILER_EFFICIENCY, default=conf_boiler_efficiency
        #         ): float,
        #         vol.Optional(
        #             CONF_BOILER_NOMINAL_POWER, default=conf_boiler_nominal_power
        #         ): float,
        #         vol.Optional(
        #             CONF_PELLET_NOMINAL_ENERGY, default=conf_pellet_nominal_energy
        #         ): float,
        #         vol.Optional(
        #             OPT_LAST_BOILER_RUN_TIME, default=last_boiler_run_time
        #         ): float,
        #         vol.Optional(OPT_LAST_ENERGY_OUTPUT, default=last_energy_output): float,
        #         vol.Optional(
        #             OPT_LAST_PELLET_CONSUMPTION, default=last_pellet_consumption
        #         ): float,
        #         vol.Optional(OPT_LAST_TIMESTAMP, default=last_timestamp): float,
        #     }
        # )

        # TODO add these sensors to defaults
        # sensor_boiler_run_time = self.hass.states.get("sensor.boiler_run_time")
        # sensor_energy_output = self.hass.states.get("sensor.energy_output")
        # sensor_pellet_consumption = self.hass.states.get("sensor.pellet_consumption")
        # sensor_last_timestamp = self.hass.states.get("sensor.last_timestamp")
        defaults = {**self.config_entry.data, **self.config_entry.options}
        schema = data_schema(defaults)

        if user_input is not None:
            # We got user input, so save it

            errors: Dict[str, str] = {}

            if not errors:
                return self.async_create_entry(title=DEFAULT_NAME, data=user_input)
            else:
                # We got errors, so show error form
                # TODO clone and set default= in data schema
                return self.async_show_form(
                    step_id="init", data_schema=schema, errors=errors
                )
        else:
            # We haven't gotten user input yet, so display form

            # TODO clone and set default= in data schema
            return self.async_show_form(step_id="init", data_schema=schema)


async def options_update_listener(hass: HomeAssistant, config_entry: ConfigEntry):
    """Handle options update."""

    # TODO Save these?
    # conf_unique_id = self.config_entry.data.get(CONF_UNIQUE_ID)
    # conf_host = self.config_entry.data.get(CONF_HOST)
    # conf_model = self.config_entry.data.get(CONF_MODEL)
    # conf_port = self.config_entry.data.get(CONF_PORT)
    # conf_protocol = self.config_entry.data.get(CONF_PROTOCOL)
    # conf_sender = self.config_entry.data.get(CONF_SENDER)
    # conf_timeout = self.config_entry.data.get(CONF_TIMEOUT)
    # conf_boiler_efficiency = self.config_entry.data.get(CONF_BOILER_EFFICIENCY)
    # conf_boiler_nominal_power = self.config_entry.data.get(CONF_BOILER_NOMINAL_POWER)
    # conf_pellet_nominal_energy = self.config_entry.data.get(CONF_PELLET_NOMINAL_ENERGY)
    # # FIXME these sensors need to be prefixed with {model}_{unique_id}_
    # sensor_boiler_run_time = self.hass.states.get('sensor.boiler_run_time')
    # sensor_energy_output = self.hass.states.get('sensor.energy_output')
    # sensor_pellet_consumption = self.hass.states.get('sensor.pellet_consumption')
    # sensor_last_timestamp = self.hass.states.get('sensor.last_timestamp')
    # last_boiler_run_time = float(sensor_boiler_run_time.state) if sensor_boiler_run_time else 0.0
    # last_energy_output = float(sensor_energy_output.state) if sensor_energy_output else 0.0
    # last_pellet_consumption = float(sensor_pellet_consumption.state) if sensor_pellet_consumption else 0.0
    # last_timestamp = float(sensor_last_timestamp.state) if sensor_last_timestamp else time.time_ns() / 1000000

    await hass.config_entries.async_reload(config_entry.entry_id)
