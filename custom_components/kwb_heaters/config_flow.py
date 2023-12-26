"""KWB Heater config flow."""

from __future__ import annotations

import logging
from pprint import pformat
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import (
    CONF_HOST,
    CONF_MODEL,
    CONF_PORT,
    CONF_PROTOCOL,
    CONF_SENDER,
    CONF_TIMEOUT,
    CONF_UNIQUE_ID,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import selector

from .const import (
    DEFAULT_NAME, 
    DOMAIN,
    CONF_PELLET_NOMINAL_ENERGY,
    CONF_BOILER_EFFICIENCY,
    CONF_BOILER_NOMINAL_POWER
)
from .heater import connect_heater

logger = logging.getLogger(__name__)


# This is the schema that used to display the UI to the user.
DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_UNIQUE_ID, default="KWB"): str,
        vol.Required(CONF_MODEL, default="easyfire_1"): selector(
            {
                "select": {
                    "options": ["easyfire_1"],
                }
            }
        ),
        vol.Required(CONF_SENDER, default="comfort_3"): selector(
            {
                "select": {
                    "options": ["comfort_3"],
                }
            }
        ),
        vol.Required(CONF_PROTOCOL, default="tcp"): selector(
            {
                "select": {
                    "options": ["tcp"],
                }
            }
        ),
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=8899): int,
        vol.Required(CONF_TIMEOUT, default=2): int,
        vol.Optional(CONF_BOILER_EFFICIENCY): float,
        vol.Optional(CONF_BOILER_NOMINAL_POWER): float,
        vol.Optional(CONF_PELLET_NOMINAL_ENERGY): float,
    }
)


class KWBConfigFlow(ConfigFlow, domain=DOMAIN):
    """KWB config flow."""

    VERSION = 1

    async def validate_input(
        self, hass: HomeAssistant, user_input: dict = None
    ) -> dict[str, Any]:
        """Validate that the user input allows us to connect to the heater.
        Data has the keys from DATA_SCHEMA with values provided by the user.
        """
        from pprint import pprint, pformat

        print(user_input)
        logger.error(pformat(user_input))
        pprint(user_input)

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
            return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)
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
                    step_id="user", data_schema=DATA_SCHEMA, errors=errors
                )
