import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .src.impl.appliance import Appliance

logger = logging.getLogger(__name__)


def data_updater(appliance: Appliance):
    """Function called by DataUpdateCoordinator to do the data refresh from the heater"""

    def u():
        try:
            is_success = appliance.scrape()
            logger.debug("data_updater is_success=%s", is_success)
        except Exception as e:
            logger.error("Failed scraping KWB heater", exc_info=e)
            raise UpdateFailed("Failed scraping KWB heater")

        if not is_success or appliance.latest_scrape == {}:
            logger.error("Failed scraping KWB heater")
            raise UpdateFailed("Failed scraping KWB heater")

        return appliance

    return u


class Coordinator(DataUpdateCoordinator):
    async def _async_update_data(self):
        """Data update coordinator implementation.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
