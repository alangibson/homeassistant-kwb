"""Glue code that allows HomeAssistant to get data from pykwb
"""

import logging

from pykwb.kwb import KWBMessageStreamLogkwb, TCPByteReader, load_signal_maps

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TIMEOUT, CONF_UNIQUE_ID
from homeassistant.helpers.update_coordinator import UpdateFailed

logger = logging.getLogger(__name__)


class KWBHeater:
    def __init__(self, config, signal_maps):
        reader = TCPByteReader(ip=config.get(CONF_HOST), port=config.get(CONF_PORT))
        self.unique_id = config.get(CONF_UNIQUE_ID)
        self.unique_key = config.get(CONF_UNIQUE_ID).lower().replace(" ", "_")
        self.message_stream = KWBMessageStreamLogkwb(reader, signal_maps)
        # FIXME remove hard coded ids
        self.message_ids = [32, 33, 64, 65]
        self.read_timeout = config.get(CONF_TIMEOUT)
        # TODO support serial too
        # if args.mode == PROP_MODE_TCP:
        #     reader = TCPByteReader(ip=args.hostname, port=args.port)
        # elif args.mode == PROP_MODE_SERIAL:
        #   reader = SerialByteReader(dev=args.interface, baud=args.baud)

        # State variables
        self.latest_scrape = {}

    def scrape(self):
        self.message_stream.open()
        message_generator = self.message_stream.read_messages(
            self.message_ids, self.read_timeout
        )
        for message in message_generator:
            data = message.decode()
            # Put data in latest_scrape
            for sensor_name, sensor_data in data.items():
                # Prepend unique id to sensor name
                sensor_value = sensor_data[0]
                sensor_definition = sensor_data[1]
                self.latest_scrape[sensor_name] = sensor_value

        self.message_stream.close()

        return True


def create_heater(config_heater: dict) -> tuple[bool, KWBHeater | Exception]:
    def f():
        try:
            signal_maps = load_signal_maps()
            heater = KWBHeater(config_heater, signal_maps)
            is_success = heater.scrape()
        except Exception as e:
            return False, e
        return is_success, heater

    return f


def connect_heater(config_heater: dict) -> tuple[bool, KWBHeater | Exception]:
    """Called by config_flow.py"""

    def f():
        try:
            is_success, heater = create_heater(config_heater)()
        except Exception as e:
            return False, e

        return is_success, heater

    return f


def data_updater(heater: KWBHeater):
    """Function called by DataUpdateCoordinator to do the data refresh from the heater"""

    def u():
        is_success = heater.scrape()
        if not is_success or heater.latest_scrape == {}:
            raise UpdateFailed("Failed scraping KWB heater")
        return heater

    return u
