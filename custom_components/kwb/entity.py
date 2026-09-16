"""Common entity metadata for KWB values."""

from typing import override

from homeassistant.helpers.entity import DeviceInfo, Entity
from pykwb import kwb

from .const import DOMAIN


class KWBEntity(Entity):
    """A value supplied by the shared KWB connection."""

    def __init__(
        self,
        easyfire: kwb.KWBEasyfire,
        sensor: kwb.KWBEasyfireSensor,
        client_name: str,
        entry_id: str | None = None,
    ) -> None:
        """Initialize the KWB sensor."""
        self._easyfire = easyfire
        self._sensor = sensor
        self._client_name = client_name
        self._name = self._sensor.name
        if entry_id is not None:
            self._attr_unique_id = f"{entry_id}_{sensor.name}"
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, entry_id)},
                name=client_name,
                manufacturer="KWB",
                model="Easyfire",
            )

    @property
    @override
    def name(self):
        """Return the name."""
        return f"{self._client_name} {self._name}"

    @property
    @override
    def available(self) -> bool:
        """Return if sensor is available."""
        return self._sensor.available
