"""Editable calculation values, persistence, and live sensor updates."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from homeassistant.exceptions import HomeAssistantError

from custom_components.kwb_heaters.config_flow import PROPERTIES_SCHEMA
from custom_components.kwb_heaters.const import PROPERTY_DEFAULTS
from custom_components.kwb_heaters.number import DESCRIPTIONS, KWBPropertyNumber
from custom_components.kwb_heaters.number import async_setup_entry as setup_numbers
from custom_components.kwb_heaters.sensor import async_setup_entry as setup_sensors


class NumberTests(unittest.IsolatedAsyncioTestCase):
    async def test_defaults_and_updates(self):
        for _ in range(2):  # New setup, including after deleting and re-adding.
            config = PROPERTIES_SCHEMA({})
            for key, default in PROPERTY_DEFAULTS.items():
                self.assertEqual(config[key], default)
        source = SimpleNamespace(
            name="Heater Output",
            value=60,
            available=True,
            sensor_type=3,
            unit_of_measurement="%",
        )
        client = MagicMock()
        client.get_sensors.return_value = [source]
        entry = SimpleNamespace(
            entry_id="heater",
            options={},
            data={"name": "Basement", **PROPERTY_DEFAULTS},
            runtime_data=client,
            async_on_unload=MagicMock(),
        )
        hass = MagicMock()

        def save(config_entry, *, options):
            config_entry.options = options

        hass.config_entries.async_update_entry.side_effect = save
        sensors = []
        with (
            patch("custom_components.kwb_heaters.sensor.er.async_get"),
            patch("custom_components.kwb_heaters.sensor.async_dispatcher_connect") as connect,
        ):
            await setup_sensors(hass, entry, sensors.extend)
        on_change = connect.call_args.args[2]
        for sensor in sensors:
            sensor.async_write_ha_state = MagicMock()
        power, _, mass, volume, consumption, cost = sensors[1:]
        self.assertEqual(consumption.native_value, 0)
        numbers = []
        with patch("custom_components.kwb_heaters.number.er.async_get") as registry:
            registry.return_value.async_get_entity_id.side_effect = [
                None,
                "sensor.old_power",
                None,
                None,
                None,
            ]
            await setup_numbers(hass, entry, numbers.extend)
            registry.return_value.async_remove.assert_called_once_with(
                "sensor.old_power"
            )
        replacements = (30, 90, 0.7, 5.0, 400)
        for number, value in zip(numbers, replacements):
            number.hass = hass
            number.async_write_ha_state = MagicMock()
            self.assertTrue(number.has_entity_name)
            self.assertEqual(number.device_info["name"], "Basement")
            self.assertFalse(number.should_poll)
            self.assertTrue(number.available)
            self.assertEqual(number.entity_category, "config")
            with patch(
                "custom_components.kwb_heaters.number.async_dispatcher_send",
                side_effect=lambda *args: on_change(),
            ):
                await number.async_set_native_value(value)
            self.assertEqual(number.native_value, value)
            restored = KWBPropertyNumber(entry, number.entity_description)
            self.assertEqual(restored.native_value, value)
        self.assertAlmostEqual(power.native_value, 18)
        self.assertAlmostEqual(mass.native_value, 18 / (0.9 * 5))
        self.assertAlmostEqual(volume.native_value, 18 / (0.9 * 5) / 0.7)
        for sensor in (power, mass, volume):
            sensor.async_write_ha_state.assert_called()
        for number in numbers:
            for invalid in (-1, float("nan"), float("inf")):
                with self.assertRaises(HomeAssistantError):
                    await number.async_set_native_value(invalid)
        for number in numbers[:-1]:
            for invalid in (0,):
                with self.assertRaises(HomeAssistantError):
                    await number.async_set_native_value(invalid)
        with self.assertRaises(HomeAssistantError):
            await numbers[1].async_set_native_value(101)
        # A replacement entry has its own defaults, not the previous options.
        fresh = SimpleNamespace(entry_id="new-heater", data=PROPERTIES_SCHEMA({}), options={})
        for description in DESCRIPTIONS:
            self.assertEqual(
                KWBPropertyNumber(fresh, description).native_value,
                PROPERTY_DEFAULTS[description.key],
            )
