"""Validate measurement classes and units against Home Assistant's contract."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor.const import DEVICE_CLASS_UNITS
from pykwb import kwb

from custom_components.kwb.sensor import KWBSensor


class SensorMetadataTests(unittest.TestCase):
    def test_measurement_classes_and_units(self):
        cases = (
            ("PROP_SENSOR_TEMPERATURE", "°C", SensorDeviceClass.TEMPERATURE, "°C"),
            ("PROP_SENSOR_PRESSURE", "mbar", SensorDeviceClass.PRESSURE, "mbar"),
            ("PROP_SENSOR_DURATION", "ms", SensorDeviceClass.DURATION, "ms"),
            ("PROP_SENSOR_DURATION", "msec", SensorDeviceClass.DURATION, "ms"),
            ("PROP_SENSOR_DURATION", "sec", SensorDeviceClass.DURATION, "s"),
            ("PROP_SENSOR_SPEED", "rpm", None, "rpm"),
            ("PROP_SENSOR_NUMBER", "%", None, "%"),
            ("PROP_SENSOR_RAW", "", None, ""),
        )
        for kind, unit, device_class, expected_unit in cases:
            with self.subTest(kind=kind, unit=unit):
                if not hasattr(kwb, kind):
                    continue  # These types are only in the local development library.
                source = SimpleNamespace(
                    name="Test",
                    sensor_type=getattr(kwb, kind),
                    unit_of_measurement=unit,
                    value=12.5,
                    available=True,
                )
                sensor = KWBSensor(MagicMock(), source, "Boiler")
                self.assertEqual(sensor.device_class, device_class)
                self.assertEqual(sensor.native_unit_of_measurement, expected_unit)
                self.assertEqual(sensor.native_value, 12.5)
                if device_class is not None:
                    self.assertIn(expected_unit, DEVICE_CLASS_UNITS[device_class])


class EnergyOutputTests(unittest.IsolatedAsyncioTestCase):
    async def test_energy_accumulation_unavailability_and_restore(self):
        from datetime import timedelta
        from decimal import Decimal
        from unittest.mock import AsyncMock, patch

        from homeassistant.components.sensor import RestoreSensor
        from homeassistant.core import State
        from homeassistant.util import dt as dt_util

        from custom_components.kwb.sensor import KWBEnergyOutputSensor

        power = MagicMock()
        power.device_info = {"identifiers": {("kwb", "heater")}}
        energy = KWBEnergyOutputSensor(power, "sensor.boiler_power", "heater", "Boiler")
        energy.hass = MagicMock()
        energy.async_write_ha_state = MagicMock()
        start = dt_util.utcnow()

        def state(value, minutes):
            timestamp = start + timedelta(minutes=minutes)
            return State(
                "sensor.boiler_power",
                str(value),
                {"unit_of_measurement": "kW", "device_class": "power"},
                last_updated=timestamp,
                last_reported=timestamp,
            )

        # 12 kW for 30 minutes, followed by shutdown: no trapezoidal undercount.
        energy._integrate_on_state_change(None, None, state(12, 0), state(0, 30))
        self.assertEqual(energy.native_value, Decimal("6"))
        self.assertEqual(energy.native_unit_of_measurement, "kWh")
        self.assertEqual(energy.device_class, SensorDeviceClass.ENERGY)
        self.assertEqual(energy.state_class, "total")
        energy._integrate_on_state_change(
            None, None, state(0, 30), state("unavailable", 40)
        )
        self.assertFalse(energy.available)
        energy._integrate_on_state_change(
            None, None, state("unavailable", 40), state(12, 100)
        )
        self.assertTrue(energy.available)
        self.assertEqual(energy.native_value, Decimal("6"))

        restored = KWBEnergyOutputSensor(
            power, "sensor.boiler_power", "heater", "Boiler"
        )
        restored.hass = MagicMock()
        restored.hass.states.get.return_value = state(12, 100)
        restored.async_write_ha_state = MagicMock()
        restored.async_get_last_state = AsyncMock(return_value=None)
        restored.async_get_last_sensor_data = AsyncMock(
            return_value=energy.extra_restore_state_data
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
            patch(
                "homeassistant.components.integration.sensor.dt_util.utcnow",
                return_value=start,
            ),
        ):
            await restored.async_added_to_hass()
            self.assertEqual(restored.native_value, Decimal("6"))
            self.assertEqual(restored.native_unit_of_measurement, "kWh")
            self.assertEqual(schedule.call_args.args[1], timedelta(minutes=1))
            # A constant reading still accumulates energy on the timer.
            restored._last_integration_time = start
            schedule.call_args.args[2](start + timedelta(minutes=1))
            self.assertEqual(restored.native_value, Decimal("6.2"))


class PelletConsumptionTests(unittest.IsolatedAsyncioTestCase):
    async def test_mass_accumulation_unavailability_and_restore(self):
        from datetime import timedelta
        from decimal import Decimal
        from unittest.mock import AsyncMock, patch

        from homeassistant.components.sensor import RestoreSensor
        from homeassistant.core import State
        from homeassistant.util import dt as dt_util

        from custom_components.kwb.sensor import KWBPelletConsumptionSensor

        power = MagicMock()
        power.device_info = {"identifiers": {("kwb", "heater")}}
        energy = KWBPelletConsumptionSensor(power, "sensor.boiler_pellet_rate", "heater", "Boiler")
        energy.hass = MagicMock()
        energy.async_write_ha_state = MagicMock()
        self.assertEqual(energy.native_value, 0)
        self.assertEqual(energy.suggested_display_precision, 2)
        start = dt_util.utcnow()

        def state(value, minutes):
            timestamp = start + timedelta(minutes=minutes)
            return State(
                "sensor.boiler_pellet_rate",
                str(value),
                {"unit_of_measurement": "kg/h"},
                last_updated=timestamp,
                last_reported=timestamp,
            )

        # 12 kg/h for 30 minutes, followed by shutdown.
        energy._integrate_on_state_change(None, None, state(12, 0), state(0, 30))
        self.assertEqual(energy.native_value, Decimal("6"))
        self.assertEqual(energy.native_unit_of_measurement, "kg")
        self.assertEqual(energy.device_class, SensorDeviceClass.WEIGHT)
        self.assertEqual(energy.state_class, "total_increasing")
        energy._integrate_on_state_change(
            None, None, state(0, 30), state("unavailable", 40)
        )
        self.assertFalse(energy.available)
        energy._integrate_on_state_change(
            None, None, state("unavailable", 40), state(12, 100)
        )
        self.assertTrue(energy.available)
        self.assertEqual(energy.native_value, Decimal("6"))

        # A calibration change alters only the subsequent rate.
        energy._integrate_on_state_change(None, None, state(12, 100), state(6, 130))
        self.assertEqual(energy.native_value, Decimal("12"))
        energy._integrate_on_state_change(None, None, state(6, 130), state(0, 160))
        self.assertEqual(energy.native_value, Decimal("15"))
        # Losing the source while burning must not bridge the unknown interval.
        energy._integrate_on_state_change(None, None, state(0, 160), state(12, 170))
        energy._integrate_on_state_change(
            None, None, state(12, 170), state("unavailable", 180)
        )
        energy._integrate_on_state_change(
            None, None, state("unavailable", 180), state(12, 240)
        )
        self.assertEqual(energy.native_value, Decimal("15"))

        restored = KWBPelletConsumptionSensor(
            power, "sensor.boiler_pellet_rate", "heater", "Boiler"
        )
        restored.hass = MagicMock()
        restored.hass.states.get.return_value = state(12, 100)
        restored.async_write_ha_state = MagicMock()
        restored.async_get_last_state = AsyncMock(return_value=None)
        restored.async_get_last_sensor_data = AsyncMock(
            return_value=energy.extra_restore_state_data
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
            patch(
                "homeassistant.components.integration.sensor.dt_util.utcnow",
                return_value=start,
            ),
        ):
            await restored.async_added_to_hass()
            self.assertEqual(restored.native_value, Decimal("15"))
            self.assertEqual(restored.native_unit_of_measurement, "kg")
            self.assertEqual(schedule.call_args.args[1], timedelta(minutes=1))
            # A constant reading still accumulates energy on the timer.
            restored._last_integration_time = start
            schedule.call_args.args[2](start + timedelta(minutes=1))
            self.assertEqual(restored.native_value, Decimal("15.2"))


class PelletRateTests(unittest.IsolatedAsyncioTestCase):
    async def test_setup_calculations_and_availability(self):
        from unittest.mock import patch

        from custom_components.kwb.sensor import async_setup_entry

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
            async_on_unload=MagicMock(),
            runtime_data=client,
            data={
                "name": "Boiler",
                "nominal_power": 25,
                "boiler_efficiency": 90,
                "pellet_energy": 4.8,
            },
        )
        sensors = []
        with patch("custom_components.kwb.sensor.er.async_get") as registry:
            registry.return_value.async_get_or_create.side_effect = [
                SimpleNamespace(entity_id="sensor.power"),
                SimpleNamespace(entity_id="sensor.renamed_pellet_rate"),
                SimpleNamespace(entity_id="sensor.renamed_pellet_total"),
            ]
            await async_setup_entry(MagicMock(), entry, sensors.extend)
        self.assertEqual(
            sensors[5].extra_state_attributes["source"],
            "sensor.renamed_pellet_rate",
        )
        mass, volume = sensors[3:5]
        self.assertEqual(len(sensors), 7)
        self.assertAlmostEqual(mass.native_value, 15 / (0.9 * 4.8))
        self.assertAlmostEqual(volume.native_value, 15 / (0.9 * 4.8) / 0.65)
        self.assertEqual(mass.native_unit_of_measurement, "kg/h")
        self.assertIsNone(mass.device_class)
        self.assertEqual(volume.device_class, SensorDeviceClass.VOLUME_FLOW_RATE)
        self.assertIn(
            volume.native_unit_of_measurement, DEVICE_CLASS_UNITS[volume.device_class]
        )
        self.assertEqual(volume.native_unit_of_measurement, "L/h")
        self.assertEqual(mass.unique_id, "heater_Pellet Consumption Rate")
        self.assertEqual(volume.unique_id, "heater_Pellet Volume Flow Rate")
        for sensor in (mass, volume):
            self.assertEqual(sensor.state_class, "measurement")
            self.assertEqual(sensor.device_info, sensors[0].device_info)
        source.value = 0
        self.assertEqual(mass.native_value, 0)
        self.assertEqual(volume.native_value, 0)
        for value in (None, -1, float("nan"), float("inf")):
            source.value = value
            self.assertIsNone(mass.native_value)
            self.assertIsNone(volume.native_value)
        source.value = 60
        source.available = False
        for sensor in (mass, volume):
            self.assertFalse(sensor.available)
            self.assertIsNone(sensor.native_value)
        source.available = True
        self.assertAlmostEqual(volume.native_value, 15 / (0.9 * 4.8) / 0.65)
        entry.data["pellet_bulk_density"] = 0.7
        sensors = []
        with patch("custom_components.kwb.sensor.er.async_get"):
            await async_setup_entry(MagicMock(), entry, sensors.extend)
        self.assertAlmostEqual(sensors[4].native_value, 15 / (0.9 * 4.8) / 0.7)
        for missing in ("nominal_power", "boiler_efficiency", "pellet_energy"):
            config = dict(entry.data)
            del entry.data[missing]
            sensors = []
            with patch("custom_components.kwb.sensor.er.async_get"):
                await async_setup_entry(MagicMock(), entry, sensors.extend)
            self.assertFalse(
                any("_Pellet " in (sensor.unique_id or "") for sensor in sensors)
            )
            entry.data = config

    async def test_configuration_validation_and_persistence(self):
        from unittest.mock import AsyncMock, patch

        import voluptuous as vol

        from custom_components.kwb.config_flow import USER_SCHEMA, KWBConfigFlow

        self.assertEqual(USER_SCHEMA({})["pellet_bulk_density"], 0.65)
        for field in ("pellet_bulk_density", "boiler_efficiency", "pellet_energy"):
            for invalid in (0, -1, float("inf"), float("nan"), "invalid"):
                with (
                    self.subTest(field=field, invalid=invalid),
                    self.assertRaises(vol.Invalid),
                ):
                    USER_SCHEMA({field: invalid})
        with self.assertRaises(vol.Invalid):
            USER_SCHEMA({"boiler_efficiency": 101})
        flow = KWBConfigFlow()
        flow.hass = MagicMock()
        flow.hass.async_add_executor_job = AsyncMock()
        flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = None
        flow._async_in_progress = MagicMock(return_value=[])
        flow.context = {"source": "user"}
        flow.handler = "kwb"
        flow.flow_id = "pellet-test"
        config = USER_SCHEMA(
            {
                "nominal_power": 25,
                "boiler_efficiency": 90,
                "pellet_energy": 4.8,
                "pellet_bulk_density": 0.7,
            }
        )
        form = await flow.async_step_user(config)
        with patch("custom_components.kwb.config_flow.validate_connection"):
            result = await flow.async_step_tcp(form["data_schema"]({"host": "boiler"}))
        for key, value in config.items():
            self.assertEqual(result["data"][key], value)
