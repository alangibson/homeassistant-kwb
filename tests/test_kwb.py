"""Exercise the KWB flow and lifecycle without connecting to a real heater."""

import asyncio
import json
import socket
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import Platform
from homeassistant.data_entry_flow import AbortFlow, FlowResultType
from homeassistant.exceptions import ConfigEntryNotReady
from pykwb import kwb

from custom_components.kwb_heaters import async_setup_entry, async_unload_entry
from custom_components.kwb_heaters.binary_sensor import KWBBinarySensor
from custom_components.kwb_heaters.binary_sensor import (
    async_setup_entry as setup_binary_sensors,
)
from custom_components.kwb_heaters.binary_sensor import (
    setup_platform as setup_binary_platform,
)
from custom_components.kwb_heaters.client import (
    KWBClient,
    create_client,
    validate_connection,
)
from custom_components.kwb_heaters.config_flow import KWBConfigFlow, vol
from custom_components.kwb_heaters.sensor import PLATFORM_SCHEMA, async_setup_platform
from custom_components.kwb_heaters.sensor import async_setup_entry as setup_sensors


class FlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.flow = KWBConfigFlow()
        self.flow.hass = MagicMock()
        self.flow.hass.async_add_executor_job = AsyncMock(
            side_effect=lambda func, *args: func(*args)
        )
        self.flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = (
            None
        )
        self.flow._async_in_progress = MagicMock(return_value=[])
        self.flow.context = {"source": "user"}
        self.flow.handler = "kwb_heaters"
        self.flow.flow_id = "test-flow"

    async def start(self, connection):
        form = await self.flow.async_step_user()
        data = form["data_schema"]({"name": " Basement heater ", "type": connection})
        return await self.flow.async_step_user(data)

    async def test_serial_and_tcp(self):
        for connection, inputs, expected_id in (
            ("serial", {"device": "/dev/ttyUSB0"}, "serial:/dev/ttyUSB0"),
            ("tcp", {"host": "BOILER.local"}, "tcp:boiler.local:23"),
        ):
            with self.subTest(connection=connection):
                form = await self.start(connection)
                self.assertEqual(form["step_id"], connection)
                data = form["data_schema"](inputs)
                with patch(
                    "custom_components.kwb_heaters.config_flow.validate_connection"
                ) as check:
                    result = await getattr(self.flow, f"async_step_{connection}")(data)
                self.assertEqual(result["step_id"], "properties")
                self.assertTrue(result["last_step"])
                result = await self.flow.async_step_properties(result["data_schema"]({}))
                self.assertEqual(result["type"], FlowResultType.CREATE_ENTRY)
                self.assertEqual(result["title"], "Basement heater")
                self.assertFalse(result["data"]["raw"])
                self.assertEqual(self.flow.unique_id, expected_id)
                check.assert_called_once()
                self.assertEqual(check.call_args.args[0]["type"], connection)
                self.assertEqual(result["data"]["heater_model"], "easyfire_1")
                self.assertEqual(result["data"]["controller"], "comfort_3")

    async def test_connection_failure_and_retry(self):
        for connection, inputs in (
            ("serial", {"device": "/dev/missing"}),
            ("tcp", {"host": "offline.local"}),
        ):
            with self.subTest(connection=connection):
                form = await self.start(connection)
                data = form["data_schema"](inputs)
                step = getattr(self.flow, f"async_step_{connection}")
                with patch(
                    "custom_components.kwb_heaters.config_flow.validate_connection",
                    side_effect=OSError,
                ):
                    result = await step(data)
                self.assertEqual(result["errors"], {"base": "cannot_connect"})
                with patch("custom_components.kwb_heaters.config_flow.validate_connection"):
                    result = await step(data)
                self.assertEqual(result["step_id"], "properties")
                self.assertTrue(result["last_step"])
                result = await self.flow.async_step_properties(result["data_schema"]({}))
                self.assertEqual(result["type"], FlowResultType.CREATE_ENTRY)

    async def test_duplicate(self):
        form = await self.start("tcp")
        self.flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = (
            SimpleNamespace(source="user")
        )
        with patch("custom_components.kwb_heaters.config_flow.validate_connection") as check:
            with self.assertRaises(AbortFlow) as raised:
                await self.flow.async_step_tcp(
                    form["data_schema"]({"host": "boiler.local"})
                )
        self.assertEqual(raised.exception.reason, "already_configured")
        check.assert_not_called()

    async def test_nominal_power_saved(self):
        form = await self.start("tcp")
        with patch("custom_components.kwb_heaters.config_flow.validate_connection"):
            form = await self.flow.async_step_tcp(
                form["data_schema"]({"host": "boiler"})
            )
        for power in (0, -1, "invalid", float("inf"), float("nan")):
            with self.subTest(power=power), self.assertRaises(vol.Invalid):
                form["data_schema"]({"nominal_power": power})
        result = await self.flow.async_step_properties(
            form["data_schema"]({"nominal_power": 25.5})
        )
        self.assertEqual(result["data"]["nominal_power"], 25.5)

    async def test_heater_selection(self):
        form = await self.flow.async_step_user()
        schema = form["data_schema"]
        self.assertEqual(
            [key.schema for key in schema.schema],
            ["name", "heater_model", "controller", "type"],
        )
        self.assertFalse(form["last_step"])
        for field in ("heater_model", "controller", "type"):
            self.assertEqual(schema.schema[field].config["mode"], "dropdown")
            with self.assertRaises(vol.Invalid):
                schema({field: "unsupported"})
        for model in ("easyfire_1", "easyfire_2"):
            form = await self.flow.async_step_user(schema({"heater_model": model}))
            with patch("custom_components.kwb_heaters.config_flow.validate_connection"):
                form = await self.flow.async_step_tcp(
                    form["data_schema"]({"host": "boiler"})
                )
            result = await self.flow.async_step_properties(form["data_schema"]({}))
            self.assertEqual(result["data"]["heater_model"], model)
            self.assertEqual(result["data"]["controller"], "comfort_3")

    async def test_input_validation(self):
        form = await self.flow.async_step_user()
        with self.assertRaises(vol.Invalid):
            form["data_schema"]({"name": " ", "type": "tcp"})
        form = await self.start("tcp")
        for port in (0, 65536, "invalid"):
            with self.assertRaises(vol.Invalid):
                form["data_schema"]({"host": "boiler.local", "port": port})


class EntryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.hass = MagicMock()
        self.hass.async_add_executor_job = AsyncMock(
            side_effect=lambda func, *args: func(*args)
        )
        self.hass.config_entries.async_forward_entry_setups = AsyncMock()
        self.hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        self.entry = MagicMock()
        self.entry.entry_id = "heater-one"
        self.entry.options = {}
        self.entry.data = {
            "name": "Basement",
            "type": "tcp",
            "host": "boiler",
            "port": 23,
        }

    async def test_setup_stop_unload(self):
        client = MagicMock()
        client.async_stop = AsyncMock()
        with patch("custom_components.kwb_heaters.create_client", return_value=client):
            self.assertTrue(await async_setup_entry(self.hass, self.entry))
        client.async_start.assert_called_once_with(self.hass)
        self.hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(
            self.entry,
            [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.NUMBER, Platform.BUTTON],
        )
        self.assertIs(self.entry.runtime_data, client)
        stop_callback = self.hass.bus.async_listen_once.call_args.args[1]
        await stop_callback(MagicMock())
        self.assertTrue(await async_unload_entry(self.hass, self.entry))
        self.assertEqual(client.async_stop.await_count, 2)

    async def test_setup_failure_retries(self):
        with patch("custom_components.kwb_heaters.create_client", side_effect=OSError):
            with self.assertRaises(ConfigEntryNotReady):
                await async_setup_entry(self.hass, self.entry)

    async def test_platform_failure_closes_client(self):
        client = MagicMock()
        client.async_stop = AsyncMock()
        self.hass.config_entries.async_forward_entry_setups.side_effect = RuntimeError
        with patch("custom_components.kwb_heaters.create_client", return_value=client):
            with self.assertRaises(RuntimeError):
                await async_setup_entry(self.hass, self.entry)
        client.async_stop.assert_awaited_once_with(self.hass)

    async def test_failed_unload_keeps_connection(self):
        self.hass.config_entries.async_unload_platforms.return_value = False
        self.assertFalse(await async_unload_entry(self.hass, self.entry))
        self.entry.runtime_data.async_stop.assert_not_called()

    async def test_real_pykwb_sensor_list(self):
        with patch.object(KWBClient, "_open_connection"):
            client = create_client(self.entry.data)
        self.entry.runtime_data = client
        sensors = []
        await setup_sensors(self.hass, self.entry, sensors.extend)
        expected_count = sum(
            sensor.sensor_type not in (kwb.PROP_SENSOR_FLAG, kwb.PROP_SENSOR_RAW)
            for sensor in client.get_sensors()
        )
        self.assertEqual(len(sensors), expected_count)
        self.assertEqual(len({sensor.unique_id for sensor in sensors}), expected_count)
        self.assertTrue(all(sensor.name.startswith("Basement ") for sensor in sensors))
        self.assertTrue(
            all(sensor.device_info["name"] == "Basement" for sensor in sensors)
        )
        self.assertFalse(sensors[0].available)
        sensors[0]._sensor.value = 42.5
        self.assertTrue(sensors[0].available)
        self.assertEqual(sensors[0].native_value, 42.5)
        self.entry.data["raw"] = True
        sensors = []
        await setup_sensors(self.hass, self.entry, sensors.extend)
        raw_count = sum(
            sensor.sensor_type == kwb.PROP_SENSOR_RAW for sensor in client.get_sensors()
        )
        self.assertEqual(len(sensors), expected_count + raw_count)
        flags = []
        await setup_binary_sensors(self.hass, self.entry, flags.extend)
        self.assertEqual(
            len(flags),
            sum(s.sensor_type == kwb.PROP_SENSOR_FLAG for s in client.get_sensors()),
        )
        self.assertTrue(all(isinstance(flag, KWBBinarySensor) for flag in flags))

    async def test_power_output(self):
        source = SimpleNamespace(
            name="Heater Output",
            sensor_type=3,
            value=50,
            available=True,
            unit_of_measurement="%",
        )
        existing_power = SimpleNamespace(
            name="Heater Power Output",
            sensor_type=3,
            value=None,
            available=False,
            unit_of_measurement="kW",
        )
        for sources in ([source], [source, existing_power]):
            self.entry.runtime_data.get_sensors.return_value = sources
            self.entry.data["nominal_power"] = 25.5
            sensors = []
            with patch("custom_components.kwb_heaters.sensor.er.async_get") as get_registry:
                registry = get_registry.return_value
                registry.async_get_or_create.return_value.entity_id = (
                    "sensor.renamed_power"
                )
                await setup_sensors(self.hass, self.entry, sensors.extend)
            self.assertEqual(len(sensors), 3)
            power = sensors[1]
            energy = sensors[2]
            self.assertEqual(energy.name, "Basement Heater Energy Output")
            self.assertEqual(energy.unique_id, "heater-one_Heater Energy Output")
            self.assertEqual(energy.device_info, power.device_info)
            self.assertEqual(
                energy.extra_state_attributes["source"], "sensor.renamed_power"
            )
            self.assertEqual(power.name, "Basement Heater Power Output")
            self.assertEqual(power.unique_id, "heater-one_Heater Power Output")
            self.assertEqual(power.device_info, sensors[0].device_info)
            self.assertEqual(power.native_unit_of_measurement, "kW")
            self.assertEqual(power.device_class, "power")
            self.assertEqual(power.state_class, "measurement")
            source.available = True
            for percent, expected in ((50, 12.75), (0, 0), (100, 25.5), (None, None)):
                source.value = percent
                self.assertEqual(power.native_value, expected)
            source.value = 50
            source.available = False
            self.assertFalse(power.available)
            self.assertIsNone(power.native_value)

    async def test_sensor_routing_and_flag_states(self):
        values = [
            SimpleNamespace(
                sensor_type=kind,
                name=name,
                value=value,
                available=True,
                unit_of_measurement=None,
            )
            for kind, name, value in (
                (kwb.PROP_SENSOR_TEMPERATURE, "Temperature", 42.5),
                (3, "Count", 3),  # PROP_SENSOR_NUMBER in the local pykwb checkout
                (kwb.PROP_SENSOR_FLAG, "Running", 0),
                (kwb.PROP_SENSOR_RAW, "Raw", "00"),
            )
        ]
        client = MagicMock()
        client.async_stop = AsyncMock()
        client.get_sensors.return_value = values
        self.entry.runtime_data = client
        for raw in (False, True):
            self.entry.data["raw"] = raw
            sensors, flags = [], []
            await setup_sensors(self.hass, self.entry, sensors.extend)
            await setup_binary_sensors(self.hass, self.entry, flags.extend)
            self.assertEqual(
                [s.native_value for s in sensors], [42.5, 3, "00"] if raw else [42.5, 3]
            )
            self.assertEqual(len(flags), 1)
        flag = flags[0]
        self.assertEqual(flag.name, "Basement Running")
        self.assertEqual(flag.unique_id, "heater-one_Running")
        self.assertEqual(flag.device_info, sensors[0].device_info)
        for value, available, expected in (
            (0, True, False),
            (1, True, True),
            (None, True, None),
            (1, False, None),
        ):
            values[2].value = value
            values[2].available = available
            self.assertIs(flag.is_on, expected)
            self.assertEqual(flag.available, available)

        config = PLATFORM_SCHEMA(
            {"platform": "kwb_heaters", "type": "tcp", "host": "boiler", "port": 23}
        )
        sensors = []
        with (
            patch("custom_components.kwb_heaters.sensor.create_client", return_value=client),
            patch("custom_components.kwb_heaters.sensor.discovery.async_load_platform") as load,
        ):
            await async_setup_platform(self.hass, config, sensors.extend)
        self.assertEqual(len(sensors), 2)
        flags = []
        discovered = load.call_args.args[3]
        self.assertIs(discovered["client"], client)
        setup_binary_platform(self.hass, {}, flags.extend, discovered)
        self.assertEqual(len(flags), 1)
        client.async_start.assert_called_once_with(self.hass)


class ClientTests(unittest.TestCase):
    def test_tcp_uses_pykwb_connection_management(self):
        with patch.object(kwb.KWBEasyfire, "_connect_tcp") as connect:
            client = create_client({"type": "tcp", "host": "boiler", "port": 23})
        connect.assert_called_once_with()
        self.assertTrue(client._reconnect_enabled())
        self.assertIs(KWBClient._open_connection, kwb.KWBEasyfire._open_connection)
        self.assertIs(KWBClient._close_connection, kwb.KWBEasyfire._close_connection)
        self.assertIs(KWBClient.listen_forever, kwb.KWBEasyfire.listen_forever)

    def test_tcp_probe_fails_but_runtime_retries(self):
        config = {"type": "tcp", "host": "boiler", "port": 23}
        with patch.object(kwb.KWBEasyfire, "_connect_tcp", side_effect=OSError):
            with self.assertRaises(OSError):
                validate_connection(config)
            client = create_client(config)
        self.assertTrue(client._reconnect_enabled())
        self.assertIsNone(client._socket)

    def test_tcp_probe_cleanup(self):
        sock = MagicMock()

        def connect(client):
            client._socket = sock

        with patch.object(kwb.KWBEasyfire, "_connect_tcp", connect):
            validate_connection({"type": "tcp", "host": "boiler", "port": 23})
        sock.close.assert_called_once_with()

    def test_serial_settings_and_cleanup(self):
        with patch("pykwb.kwb.serial.Serial") as serial:
            validate_connection({"type": "serial", "device": "/dev/ttyUSB0"})
        serial.assert_called_once_with("/dev/ttyUSB0", 19200)
        serial.return_value.close.assert_called()

    def test_yaml_still_supported(self):
        for data in (
            {"platform": "kwb_heaters", "type": "serial", "device": "/dev/ttyUSB0"},
            {"platform": "kwb_heaters", "type": "tcp", "host": "boiler", "port": 23},
        ):
            config = PLATFORM_SCHEMA(data)
            self.assertFalse(config["raw"])
            self.assertEqual(config["name"], "KWB")

    def test_translations(self):
        root = Path(__file__).resolve().parents[1] / "custom_components/kwb_heaters"
        strings = json.loads((root / "strings.json").read_text())
        self.assertEqual(
            strings, json.loads((root / "translations/en.json").read_text())
        )
        self.assertEqual(
            set(strings["config"]["step"]), {"user", "serial", "tcp", "properties"}
        )
        self.assertEqual(
            set(strings["selector"]["connection_type"]["options"]), {"serial", "tcp"}
        )


class AsyncListenerTests(unittest.IsolatedAsyncioTestCase):
    def make_hass(self):
        hass = MagicMock()
        hass.async_create_background_task.side_effect = lambda coro, name: (
            asyncio.create_task(coro)
        )
        hass.async_add_executor_job = AsyncMock(side_effect=lambda func: func())
        return hass

    async def test_listener_cancel(self):
        with patch.object(KWBClient, "_open_connection"):
            client = create_client({"type": "tcp", "host": "boiler", "port": 23})
        listening = asyncio.Event()

        async def listen():
            listening.set()
            await asyncio.Future()

        hass = self.make_hass()
        with (
            patch.object(client, "listen_forever", side_effect=listen) as listener,
            patch.object(client, "_close_connection") as close,
        ):
            client.async_start(hass)
            await asyncio.wait_for(listening.wait(), 1)
            await client.async_stop(hass)
            listener.assert_awaited_once_with()
            close.assert_called()
        self.assertIsNone(client._listener_task)
        self.assertFalse(client.is_alive())

    async def test_real_listener_reconnects_after_eof_and_stale_connection(self):
        import time

        for failure in ("eof", "stale", "initial"):
            with self.subTest(failure=failure):
                reader, writer = socket.socketpair()
                replacement, sender = socket.socketpair()
                replacement.setblocking(False)
                with patch.object(KWBClient, "_open_connection"):
                    client = create_client(
                        {"type": "tcp", "host": "boiler", "port": 23}
                    )
                client._socket = None if failure == "initial" else reader
                client._config["connection"]["retry_initial"] = 0.001
                client._retry_delay = 0.001
                if failure == "eof":
                    writer.close()
                elif failure == "stale":
                    client._last_valid_packet = time.monotonic() - 60
                reconnected = asyncio.Event()
                received = asyncio.Event()

                async def reconnect():
                    self.assertIsNone(client._socket)
                    client._socket = replacement
                    client._last_valid_packet = time.monotonic()
                    reconnected.set()

                hass = self.make_hass()
                try:
                    with (
                        patch.object(
                            client, "_connect_tcp_async", side_effect=reconnect
                        ) as connect,
                        patch.object(
                            client,
                            "_record_byte",
                            side_effect=lambda value: received.set(),
                        ),
                    ):
                        client.async_start(hass)
                        await asyncio.wait_for(reconnected.wait(), 1)
                        sender.sendall(b"\x02")
                        await asyncio.wait_for(received.wait(), 1)
                        self.assertFalse(client._listener_task.done())
                        connect.assert_awaited_once_with()
                        await asyncio.wait_for(client.async_stop(hass), 1)
                        self.assertIsNone(client._socket)
                        self.assertEqual(replacement.fileno(), -1)
                finally:
                    await client.async_stop(hass)
                    for sock in (reader, writer, replacement, sender):
                        sock.close()

    async def test_cancel_during_retry_delay(self):
        with patch.object(KWBClient, "_open_connection"):
            client = create_client({"type": "tcp", "host": "boiler", "port": 23})
        retrying = asyncio.Event()

        def delay():
            retrying.set()
            return 30

        hass = self.make_hass()
        with (
            patch.object(client, "_next_retry_delay", side_effect=delay),
            patch.object(client, "_connect_tcp_async") as connect,
        ):
            client.async_start(hass)
            await asyncio.wait_for(retrying.wait(), 1)
            await asyncio.wait_for(client.async_stop(hass), 1)
            connect.assert_not_called()
        self.assertIsNone(client._socket)
        self.assertIsNone(client._listener_task)
