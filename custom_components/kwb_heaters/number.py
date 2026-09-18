"""Editable local boiler and pellet calculation settings."""

import math
import sys

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import CONF_NAME, PERCENTAGE, EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import KWBConfigEntry
from .const import (
    CONF_BOILER_EFFICIENCY,
    CONF_NOMINAL_POWER,
    CONF_PELLET_BULK_DENSITY,
    CONF_PELLET_ENERGY,
    CONF_PELLET_PRICE,
    DOMAIN,
    PROPERTY_DEFAULTS,
)

DESCRIPTIONS = (
    NumberEntityDescription(
        key=CONF_NOMINAL_POWER,
        translation_key=CONF_NOMINAL_POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=NumberDeviceClass.POWER,
        native_min_value=0.01,
        native_max_value=sys.float_info.max,
        native_step=0.01,
    ),
    NumberEntityDescription(
        key=CONF_BOILER_EFFICIENCY,
        translation_key=CONF_BOILER_EFFICIENCY,
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=0.1,
        native_max_value=100,
        native_step=0.1,
    ),
    NumberEntityDescription(
        key=CONF_PELLET_BULK_DENSITY,
        translation_key=CONF_PELLET_BULK_DENSITY,
        native_unit_of_measurement="kg/L",
        native_min_value=0.01,
        native_max_value=sys.float_info.max,
        native_step=0.01,
    ),
    NumberEntityDescription(
        key=CONF_PELLET_ENERGY,
        translation_key=CONF_PELLET_ENERGY,
        native_unit_of_measurement="kWh/kg",
        native_min_value=0.1,
        native_max_value=sys.float_info.max,
        native_step=0.1,
    ),
    NumberEntityDescription(
        key=CONF_PELLET_PRICE,
        translation_key=CONF_PELLET_PRICE,
        native_min_value=0,
        native_max_value=sys.float_info.max,
        native_step=0.01,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: KWBConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Replace the old read-only property sensors with editable numbers."""
    registry = er.async_get(hass)
    for description in DESCRIPTIONS:
        old_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_config_{description.key}"
        )
        if old_id is not None:
            registry.async_remove(old_id)
    async_add_entities(
        KWBPropertyNumber(entry, description) for description in DESCRIPTIONS
    )


class KWBPropertyNumber(NumberEntity):
    """Persist a calculation setting without writing to the boiler."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(
        self, entry: KWBConfigEntry, description: NumberEntityDescription
    ) -> None:
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_config_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_NAME],
            manufacturer="KWB"
        )

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.entity_description.key == CONF_PELLET_PRICE:
            return f"{self.hass.config.currency}/t"
        return self.entity_description.native_unit_of_measurement

    @property
    def native_value(self) -> float:
        key = self.entity_description.key
        return self._entry.options.get(
            key, self._entry.data.get(key, PROPERTY_DEFAULTS[key])
        )

    async def async_set_native_value(self, value: float) -> None:
        if (
            not math.isfinite(value)
            or not self.native_min_value <= value <= self.native_max_value
        ):
            raise HomeAssistantError("Value is outside the allowed range")
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={**self._entry.options, self.entity_description.key: value},
        )
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, f"{DOMAIN}_{self._entry.entry_id}_properties")
