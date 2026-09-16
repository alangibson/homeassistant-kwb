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
