"""Reset controls for KWB calculated energy."""

from homeassistant.components.button import ButtonEntity
from homeassistant.const import CONF_NAME, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import KWBConfigEntry
from .const import (
    CONF_BOILER_EFFICIENCY,
    CONF_NOMINAL_POWER,
    CONF_PELLET_ENERGY,
    DOMAIN,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: KWBConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add a reset button whenever heater energy output is supported."""
    config = {**entry.data, **entry.options}
    if config.get(CONF_NOMINAL_POWER) is not None and any(
        sensor.name == "Heater Output" for sensor in entry.runtime_data.get_sensors()
    ):
        async_add_entities([KWBResetEnergyButton(entry)])
        if all(
            config.get(key) is not None
            for key in (CONF_BOILER_EFFICIENCY, CONF_PELLET_ENERGY)
        ):
            async_add_entities([KWBResetPelletButton(entry)])


class KWBResetEnergyButton(ButtonEntity):
    """Reset the running energy total without deleting recorded history."""

    _reset_target_key = "energy_reset_targets"
    _target_name = "Heater Energy Output"
    _unique_suffix = "reset_heater_energy_output"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:restart"
    _attr_has_entity_name = False

    def __init__(self, entry: KWBConfigEntry) -> None:
        self._entry_id = entry.entry_id
        self._attr_name = f"Reset {entry.data[CONF_NAME]} {self._target_name}"
        self._attr_unique_id = f"{entry.entry_id}_{self._unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_NAME],
            manufacturer="KWB"
        )

    async def async_press(self) -> None:
        energy = (
            self.hass.data.get(DOMAIN, {})
            .get(self._reset_target_key, {})
            .get(self._entry_id)
        )
        if energy is None:
            raise HomeAssistantError(
                f"{self._target_name} must be enabled and loaded before resetting"
            )
        energy.async_reset()


class KWBResetPelletButton(KWBResetEnergyButton):
    """Reset only the accumulated pellet mass for this heater."""

    _reset_target_key = "pellet_reset_targets"
    _target_name = "Pellet Consumption"
    _unique_suffix = "reset_pellet_consumption"
