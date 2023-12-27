"""Constants for the KWB integration"""

from datetime import timedelta

DOMAIN = "kwb_heaters"

DEFAULT_NAME = "KWB Heaters"
DEFAULT_PORT = 502
DEFAULT_SLAVE = 0x01
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_TIMEOUT = 3

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=10)

CONF_PELLET_NOMINAL_ENERGY = 'pellet_nominal_energy_kWh_kg'
CONF_BOILER_EFFICIENCY = 'boiler_efficiency'
CONF_BOILER_NOMINAL_POWER = 'boiler_nominal_power_kW'
OPT_LAST_BOILER_RUN_TIME = 'last_boiler_run_time'
OPT_LAST_ENERGY_OUTPUT = 'last_energy_output'
OPT_LAST_PELLET_CONSUMPTION = 'last_pellet_consumption'
OPT_LAST_TIMESTAMP = 'last_timestamp'
