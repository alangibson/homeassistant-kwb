"""UI configuration for KWB heaters."""

import sys
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_NAME, CONF_PORT, CONF_TYPE
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from .client import validate_connection
from .const import (
    CONF_BOILER_EFFICIENCY,
    CONF_NOMINAL_POWER,
    CONF_PELLET_BULK_DENSITY,
    CONF_PELLET_ENERGY,
    CONF_PELLET_PRICE,
    CONF_RAW,
    DEFAULT_BOILER_EFFICIENCY,
    DEFAULT_NAME,
    DEFAULT_NOMINAL_POWER,
    DEFAULT_PELLET_BULK_DENSITY,
    DEFAULT_PELLET_ENERGY,
    DEFAULT_PELLET_PRICE,
    DEFAULT_PORT,
    DEFAULT_RAW,
    DOMAIN,
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): vol.All(
            str, vol.Strip, vol.Length(min=1)
        ),
        vol.Required(CONF_TYPE, default="tcp"): SelectSelector(
            SelectSelectorConfig(
                options=["serial", "tcp"], translation_key="connection_type"
            )
        ),
        vol.Required(CONF_NOMINAL_POWER, default=DEFAULT_NOMINAL_POWER): vol.All(
            vol.Coerce(float),
            vol.Range(min=0, min_included=False, max=sys.float_info.max),
        ),
        vol.Required(
            CONF_PELLET_BULK_DENSITY, default=DEFAULT_PELLET_BULK_DENSITY
        ): vol.All(
            vol.Coerce(float),
            vol.Range(min=0, min_included=False, max=sys.float_info.max),
        ),
        vol.Required(
            CONF_BOILER_EFFICIENCY, default=DEFAULT_BOILER_EFFICIENCY
        ): vol.All(vol.Coerce(float), vol.Range(min=0, min_included=False, max=100)),
        vol.Required(CONF_PELLET_PRICE, default=DEFAULT_PELLET_PRICE): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=sys.float_info.max)
        ),
        vol.Required(CONF_PELLET_ENERGY, default=DEFAULT_PELLET_ENERGY): vol.All(
            vol.Coerce(float),
            vol.Range(min=0, min_included=False, max=sys.float_info.max),
        ),
    }
)


class KWBConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure a serial or TCP heater."""

    VERSION = 1

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a heater name and connection type."""
        if user_input is not None:
            self._config = dict(user_input)
            if user_input[CONF_TYPE] == "serial":
                return await self.async_step_serial()
            return await self.async_step_tcp()
        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the local serial device."""
        return await self._async_step_connection(
            "serial",
            vol.Schema(
                {
                    vol.Required(CONF_DEVICE, default="/dev/ttyUSB0"): vol.All(
                        str, vol.Strip, vol.Length(min=1)
                    ),
                    vol.Optional(CONF_RAW, default=DEFAULT_RAW): bool,
                }
            ),
            user_input,
        )

    async def async_step_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the serial server's TCP endpoint."""
        return await self._async_step_connection(
            "tcp",
            vol.Schema(
                {
                    vol.Required(CONF_HOST): vol.All(str, vol.Strip, vol.Length(min=1)),
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
                    vol.Optional(CONF_RAW, default=DEFAULT_RAW): bool,
                }
            ),
            user_input,
        )

    async def _async_step_connection(
        self,
        step_id: str,
        schema: vol.Schema,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """Validate the transport and avoid configuring the same endpoint twice."""
        errors: dict[str, str] = {}
        if user_input is not None:
            config = {**self._config, **user_input}
            if step_id == "serial":
                unique_id = f"serial:{config[CONF_DEVICE]}"
            else:
                config[CONF_HOST] = config[CONF_HOST].lower()
                unique_id = f"tcp:{config[CONF_HOST]}:{config[CONF_PORT]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            try:
                await self.hass.async_add_executor_job(validate_connection, config)
            except OSError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=config[CONF_NAME], data=config)
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )
