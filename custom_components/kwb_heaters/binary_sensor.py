import logging
from typing import Any, Coroutine

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_MODEL, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN

logger = logging.getLogger(__name__)

logger.error("binary sensor module loading")


def sensor_entities(
    model: str, unique_device_id: str, coordinator: DataUpdateCoordinator
):
    return [
        KWBBinarySensorCoordinatorEntity(
            coordinator=coordinator,
            entity_description=BinarySensorEntityDescription(
                device_class=BinarySensorDeviceClass.RUNNING,
                # entity_category=EntityCategory.,
                # entity_registry_enabled_default=...,
                # entity_registry_visible_default=...,
                # force_update=...,
                # has_entity_name=...,
                # icon=...,
                key="boiler_on",
                name=f"{model} {unique_device_id} Boiler On",
                translation_key="boiler_on",
                # unit_of_measurement=...
            ),
        )
    ]


class KWBBinarySensorEntity(BinarySensorEntity, RestoreEntity):
    """Custom binary sensor entity"""


class KWBBinarySensorCoordinatorEntity(CoordinatorEntity, KWBBinarySensorEntity):
    """Custom binary sensor entity"""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entity_description: BinarySensorEntityDescription,
    ):
        super().__init__(coordinator)
        self.entity_description = entity_description
        self.idx = entity_description.key

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        # TODO Put transformations here, such as:
        # self._attr_is_on = self.coordinator.data[self.idx]["state"]

        super()._handle_coordinator_update()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id].get("coordinator")
    model = config_entry.data.get(CONF_MODEL)
    unique_device_id = config_entry.data.get(CONF_UNIQUE_ID)
    async_add_entities(
        sensor_entities(model, unique_device_id, coordinator), update_before_add=True
    )
