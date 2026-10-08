"""Price validation and current-price consumption cost."""

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers.entity import Entity

from custom_components.kwb_heaters.config_flow import PROPERTIES_SCHEMA, vol
from custom_components.kwb_heaters.number import DESCRIPTIONS, KWBPropertyNumber
from custom_components.kwb_heaters.sensor import (
    KWBPelletConsumptionCostSensor,
    KWBPelletConsumptionSensor,
    KWBPelletEnergyPriceSensor,
    async_setup_entry,
)


class CostTests(unittest.IsolatedAsyncioTestCase):
    async def test_price_and_cost_updates(self):
        self.assertEqual(PROPERTIES_SCHEMA({})["pellet_price"], 0)
        for value in (-1, float("nan"), float("inf"), "invalid"):
            with self.assertRaises(vol.Invalid):
                PROPERTIES_SCHEMA({"pellet_price": value})
        entry = SimpleNamespace(
            entry_id="heater",
            data={"name": "Basement", **PROPERTIES_SCHEMA({"pellet_price": 400})},
            options={},
        )
        total = KWBPelletConsumptionSensor(
            MagicMock(), "sensor.rate", "heater", "Basement"
        )
        total._state = Decimal(250)
        total.hass = MagicMock()
        total.hass.states.get.return_value = None
        total.async_write_ha_state = MagicMock()
        cost = KWBPelletConsumptionCostSensor(
            entry, total, "sensor.renamed_total", "EUR"
        )
        cost.hass = MagicMock()
        cost.async_write_ha_state = MagicMock()
        self.assertEqual(cost.native_value, Decimal(100))
        self.assertEqual(cost.native_unit_of_measurement, "EUR")
        self.assertEqual(cost.device_class, "monetary")
        self.assertIsNone(cost.state_class)
        self.assertEqual(cost.name, "Basement Pellet Consumption Cost")
        with (
            patch.object(Entity, "async_added_to_hass", new_callable=AsyncMock),
            patch(
                "custom_components.kwb_heaters.sensor.async_track_state_change_event"
            ) as track,
            patch("custom_components.kwb_heaters.sensor.async_dispatcher_connect") as connect,
        ):
            await cost.async_added_to_hass()
            self.assertEqual(track.call_args.args[1], "sensor.renamed_total")
            self.assertEqual(connect.call_args.args[1], "kwb_heaters_heater_properties")
            number = KWBPropertyNumber(
                entry, next(d for d in DESCRIPTIONS if d.key == "pellet_price")
            )
            number.hass = MagicMock()
            number.hass.config.currency = "EUR"
            number.async_write_ha_state = MagicMock()
            number.hass.config_entries.async_update_entry.side_effect = (
                lambda e, options: setattr(e, "options", options)
            )
            self.assertEqual(number.native_unit_of_measurement, "EUR/t")
            with patch(
                "custom_components.kwb_heaters.number.async_dispatcher_send",
                side_effect=lambda *args: connect.call_args.args[2](),
            ):
                await number.async_set_native_value(500)
            cost.async_write_ha_state.assert_called()
            self.assertEqual(cost.native_value, Decimal(125))
            total._state = Decimal(500)
            track.call_args.args[2](MagicMock())
            self.assertEqual(cost.native_value, Decimal(250))
            total.async_reset()
            track.call_args.args[2](MagicMock())
            self.assertEqual(cost.native_value, Decimal(0))
            total._attr_available = False
            self.assertFalse(cost.available)
            self.assertIsNone(cost.native_value)
            total._attr_available = True
            total._state = Decimal(1000)
            self.assertEqual(cost.native_value, Decimal(500))
            with patch("custom_components.kwb_heaters.number.async_dispatcher_send"):
                await number.async_set_native_value(0)
            self.assertEqual(cost.native_value, 0)


class EnergyPriceTests(unittest.IsolatedAsyncioTestCase):
    async def test_price_and_energy_updates(self):
        entry = SimpleNamespace(
            entry_id="heater",
            data={"name": "Basement", "pellet_price": 400, "pellet_energy": 4.8},
            options={},
        )
        sensor = KWBPelletEnergyPriceSensor(entry, "EUR")
        self.assertAlmostEqual(sensor.native_value, 0.0833333333)
        self.assertEqual(sensor.native_unit_of_measurement, "€/kWh")
        self.assertEqual(sensor.icon, "mdi:currency-eur")
        self.assertEqual(sensor.unique_id, "heater_Pellet Energy Price")
        self.assertEqual(sensor.device_info["identifiers"], {("kwb_heaters", "heater")})
        self.assertEqual(sensor.state_class, "measurement")
        self.assertIsNone(sensor.device_class)
        sensor.hass = MagicMock()
        sensor.async_write_ha_state = MagicMock()
        with (
            patch.object(Entity, "async_added_to_hass", new_callable=AsyncMock),
            patch("custom_components.kwb_heaters.sensor.async_dispatcher_connect") as connect,
        ):
            await sensor.async_added_to_hass()
            self.assertEqual(connect.call_args.args[1], "kwb_heaters_heater_properties")
            for key, value, expected in (
                ("pellet_price", 480, 0.1),
                ("pellet_energy", 5, 0.096),
                ("boiler_efficiency", 80, 0.096),
                ("pellet_price", 0, 0),
            ):
                entry.options[key] = value
                connect.call_args.args[2]()
                self.assertAlmostEqual(sensor.native_value, expected)
                self.assertTrue(sensor.available)
            self.assertEqual(sensor.async_write_ha_state.call_count, 4)

    async def test_defaults_invalid_values_and_setup_without_telemetry(self):
        entry = SimpleNamespace(
            entry_id="heater", data={"name": "Basement"}, options={},
            runtime_data=MagicMock(),
        )
        entry.runtime_data.get_sensors.return_value = []
        hass = MagicMock()
        hass.config.currency = "EUR"
        sensors = []
        await async_setup_entry(hass, entry, sensors.extend)
        self.assertEqual(len(sensors), 1)
        sensor = sensors[0]
        self.assertIsInstance(sensor, KWBPelletEnergyPriceSensor)
        self.assertEqual(sensor.native_value, 0)
        for key, values in (
            ("pellet_price", [-1, None, "invalid", float("nan"), float("inf")]),
            ("pellet_energy", [0, -1, None, "invalid", float("nan"), float("inf")]),
        ):
            for value in values:
                with self.subTest(key=key, value=value):
                    entry.options = {key: value}
                    self.assertIsNone(sensor.native_value)
                    self.assertFalse(sensor.available)
        entry.options = {"pellet_price": 480}
        self.assertTrue(sensor.available)
        self.assertAlmostEqual(sensor.native_value, 0.1)
