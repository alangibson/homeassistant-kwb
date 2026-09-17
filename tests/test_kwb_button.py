"""Energy reset boundaries, restore behavior, and button routing."""

import unittest
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.sensor import RestoreSensor
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from custom_components.kwb.button import async_setup_entry
from custom_components.kwb.sensor import (
    KWBEnergyOutputSensor,
    KWBPelletConsumptionSensor,
)


class ResetTests(unittest.IsolatedAsyncioTestCase):
    async def test_button_setup_and_routing(self):
        entry = SimpleNamespace(
            entry_id="heater",
            data={"name": "Basement", "nominal_power": 25},
            options={},
            runtime_data=MagicMock(),
        )
        entry.runtime_data.get_sensors.return_value = [
            SimpleNamespace(name="Heater Output")
        ]
        buttons = []
        await async_setup_entry(MagicMock(), entry, buttons.extend)
        self.assertEqual(len(buttons), 1)
        button = buttons[0]
        self.assertEqual(button.name, "Reset Basement Heater Energy Output")
        self.assertFalse(button.has_entity_name)
        energy = MagicMock()
        other = MagicMock()
        button.hass = MagicMock()
        button.hass.data = {
            "kwb": {"energy_reset_targets": {"heater": energy, "other": other}}
        }
        await button.async_press()
        energy.async_reset.assert_called_once_with()
        other.async_reset.assert_not_called()
        button.hass.data = {}
        with self.assertRaises(HomeAssistantError):
            await button.async_press()
        entry.runtime_data.get_sensors.return_value = []
        buttons = []
        await async_setup_entry(MagicMock(), entry, buttons.extend)
        self.assertEqual(buttons, [])

    async def test_reset_time_boundary_and_restore_zero(self):
        await self.check_reset(
            KWBEnergyOutputSensor, "kW", "total", "energy_reset_targets"
        )

    async def test_pellet_reset_time_boundary_and_restore_zero(self):
        await self.check_reset(
            KWBPelletConsumptionSensor,
            "kg/h",
            "total_increasing",
            "pellet_reset_targets",
        )

    async def check_reset(self, sensor_class, unit, state_class, target_key):
        power = MagicMock()
        power.device_info = {"identifiers": {("kwb", "heater")}}
        energy = sensor_class(power, "sensor.power", "heater", "Basement")
        energy.hass = MagicMock()
        energy.hass.data = {}
        energy.async_write_ha_state = MagicMock()
        start = dt_util.utcnow()

        def state(value, seconds):
            timestamp = start + timedelta(seconds=seconds)
            return State(
                "sensor.power",
                str(value),
                {"unit_of_measurement": unit, "device_class": "power"},
                last_updated=timestamp,
                last_reported=timestamp,
            )

        energy._integrate_on_state_change(None, None, state(12, 0), state(12, 1800))
        self.assertEqual(energy.native_value, Decimal(6))
        reset_time = start + timedelta(seconds=1830)
        energy.hass.states.get.return_value = state(12, 1800)
        with (
            patch(
                "custom_components.kwb.sensor.dt_util.utcnow", return_value=reset_time
            ),
            patch("homeassistant.components.integration.sensor.async_call_later"),
        ):
            energy.async_reset()
        self.assertEqual(energy.native_value, 0)
        self.assertEqual(
            energy.last_reset, reset_time if state_class == "total" else None
        )
        self.assertEqual(energy.state_class, state_class)
        zero_data = energy.extra_restore_state_data
        # A source change 30 seconds after reset counts only those 30 seconds.
        energy._integrate_on_state_change(None, None, state(12, 1800), state(0, 1860))
        self.assertEqual(energy.native_value, Decimal("0.1"))
        # Restart from serialized zero data, exercising the actual restore decoder.
        restored = sensor_class(power, "sensor.power", "heater", "Basement")
        restored.hass = MagicMock()
        restored.hass.data = {}
        restored.hass.states.get.return_value = state(12, 1860)
        restored.async_write_ha_state = MagicMock()
        restored.async_get_last_extra_data = AsyncMock(
            return_value=SimpleNamespace(as_dict=zero_data.as_dict)
        )
        restored.async_get_last_state = AsyncMock(
            return_value=State(
                "sensor.energy",
                "0",
                (
                    {"last_reset": reset_time.isoformat()}
                    if state_class == "total"
                    else {}
                ),
            )
        )
        with (
            patch.object(RestoreSensor, "async_added_to_hass", new_callable=AsyncMock),
            patch(
                "homeassistant.components.integration.sensor.async_track_state_change_event"
            ),
            patch(
                "homeassistant.components.integration.sensor.async_track_state_report_event"
            ),
            patch(
                "homeassistant.components.integration.sensor.async_call_later"
            ) as schedule,
        ):
            await restored.async_added_to_hass()
            self.assertEqual(restored.native_value, 0)
            self.assertEqual(
                restored.last_reset, reset_time if state_class == "total" else None
            )
            self.assertIs(restored.hass.data["kwb"][target_key]["heater"], restored)
            restored._last_integration_time = start + timedelta(seconds=1860)
            schedule.call_args.args[2](start + timedelta(seconds=1920))
            self.assertEqual(restored.native_value, Decimal("0.2"))
        # A reset during an outage preserves availability and does not add downtime.
        restored._attr_available = False
        restored.hass.states.get.return_value = state("unavailable", 1920)
        with patch(
            "homeassistant.components.integration.sensor.async_call_later"
        ) as schedule:
            restored.async_reset()
            schedule.assert_not_called()
        self.assertFalse(restored.available)
        self.assertEqual(restored.native_value, 0)

    async def test_pellet_button_targets_only_its_total(self):
        entry = SimpleNamespace(
            entry_id="heater",
            data={"name": "Basement", "nominal_power": 25},
            options={"boiler_efficiency": 95, "pellet_energy": 4.8},
            runtime_data=MagicMock(),
        )
        entry.runtime_data.get_sensors.return_value = [
            SimpleNamespace(name="Heater Output")
        ]
        buttons = []
        await async_setup_entry(MagicMock(), entry, buttons.extend)
        self.assertEqual(len(buttons), 2)
        button = buttons[1]
        self.assertEqual(button.name, "Reset Basement Pellet Consumption")
        self.assertEqual(button.unique_id, "heater_reset_pellet_consumption")
        pellet, energy, other = MagicMock(), MagicMock(), MagicMock()
        button.hass = MagicMock()
        button.hass.data = {
            "kwb": {
                "pellet_reset_targets": {"heater": pellet, "other": other},
                "energy_reset_targets": {"heater": energy},
            }
        }
        await button.async_press()
        pellet.async_reset.assert_called_once_with()
        energy.async_reset.assert_not_called()
        other.async_reset.assert_not_called()
        del button.hass.data["kwb"]["pellet_reset_targets"]["heater"]
        with self.assertRaises(HomeAssistantError):
            await button.async_press()
