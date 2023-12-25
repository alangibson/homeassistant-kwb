"""Constants for the KWB integration"""

from datetime import timedelta

DOMAIN = "kwb"

DEFAULT_NAME = "KWB"
DEFAULT_PORT = 502
DEFAULT_SLAVE = 0x01
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_TIMEOUT = 3

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=10)
