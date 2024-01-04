"""Glue code that allows HomeAssistant to get data from pykwb."""

import logging

from pykwb.kwb import KWBMessageStream, TCPByteReader, load_signal_maps

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TIMEOUT, CONF_UNIQUE_ID

from ...const import (
    CONF_BOILER_EFFICIENCY,
    CONF_BOILER_NOMINAL_POWER,
    CONF_PELLET_NOMINAL_ENERGY,
    OPT_LAST_BOILER_RUN_TIME,
    OPT_LAST_ENERGY_OUTPUT,
    OPT_LAST_PELLET_CONSUMPTION,
    OPT_LAST_TIMESTAMP,
)

logger = logging.getLogger(__name__)


class Appliance:
    """A physical appliance or service."""

    def __init__(self, config, signal_maps):
        reader = TCPByteReader(ip=config.get(CONF_HOST), port=config.get(CONF_PORT))
        self.unique_id = config.get(CONF_UNIQUE_ID)
        self.unique_key = config.get(CONF_UNIQUE_ID).lower().replace(" ", "_")
        heater_config = {
            "pellet_nominal_energy_kWh_kg": config.get(CONF_PELLET_NOMINAL_ENERGY),
            "boiler_efficiency": config.get(CONF_BOILER_EFFICIENCY),
            "boiler_nominal_power_kW": config.get(CONF_BOILER_NOMINAL_POWER),
        }
        last_values = {
            "last_timestamp": config.get(OPT_LAST_TIMESTAMP),
            "boiler_run_time": config.get(OPT_LAST_BOILER_RUN_TIME),
            "boiler_energy": config.get(OPT_LAST_ENERGY_OUTPUT),
            "pellet_consumption": config.get(OPT_LAST_PELLET_CONSUMPTION),
        }
        self.message_stream = KWBMessageStream(
            reader=reader,
            signal_maps=signal_maps,
            heater_config=heater_config,
            last_values=last_values,
        )
        # FIXME remove hard coded ids
        self.message_ids = [32, 33, 64, 65]
        self.read_timeout = config.get(CONF_TIMEOUT, 2)
        # TODO support serial too
        # if args.mode == PROP_MODE_TCP:
        #     reader = TCPByteReader(ip=args.hostname, port=args.port)
        # elif args.mode == PROP_MODE_SERIAL:
        #   reader = SerialByteReader(dev=args.interface, baud=args.baud)

        # State variables
        self.latest_scrape = {}

    def scrape(self):
        self.message_stream.open()

        # TODO use read_data(), not read_messages()
        # message_generator = self.message_stream.read_messages(
        #     self.message_ids, self.read_timeout
        # )
        # for message in message_generator:
        #     data = message.decode()
        #     # Put data in latest_scrape
        #     for sensor_name, sensor_data in data.items():
        #         # Prepend unique id to sensor name
        #         sensor_value = sensor_data[0]
        #         sensor_definition = sensor_data[1]
        #         self.latest_scrape[sensor_name] = sensor_value

        data = self.message_stream.read_data_once(self.message_ids, self.read_timeout)
        self.latest_scrape.update(data)

        self.message_stream.close()

        return True


def create_appliance(config_heater: dict) -> tuple[bool, Appliance | Exception]:
    def f():
        try:
            signal_maps = load_signal_maps()
            heater = Appliance(config_heater, signal_maps)
            is_success = heater.scrape()
        except Exception as e:
            logger.error("Error connecting to heater", exc_info=e)
            return False, e
        return is_success, heater

    return f


def connect_appliance(config_heater: dict) -> tuple[bool, Appliance | Exception]:
    """Called by config_flow.py"""

    def f():
        try:
            is_success, heater = create_appliance(config_heater)()
        except Exception as e:
            return False, e

        return is_success, heater

    return f
