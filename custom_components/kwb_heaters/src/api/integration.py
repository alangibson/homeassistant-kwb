
# Configuration
DOMAIN: str = ...
MANUFACTUROR: str  = ...

class Integration:
    """"""


class Entity:
    """

    https://developers.home-assistant.io/docs/core/entity#generic-properties
    """

    # Function that returns a unique id for the entity.
    #
    # This is not the same as the entity id! Entity id is made up of a domain and an object id.
    #
    # Entity device info is only read if the entity is loaded via a config entry and the unique_id property is defined.
    # https://developers.home-assistant.io/docs/device_registry_index#automatic-registration-through-an-entity
    #
    # Defaults to Config Entry ID
    # https://developers.home-assistant.io/docs/entity_registry_index#unique-id
    f_unique_id = lambda config_entry: config_entry.entry_id


class PollableEntity(Entity):
    """Fetches or calculates its own data by occasional polling"""

    # Home Assistant will poll an entity when the should_poll property returns True (the default value).
    should_poll = True

    async def poll(self):
        """
        Poll device for data.

        https://developers.home-assistant.io/docs/core/entity#polling
        """

class SubscribingEntity(Entity):
    """Receives data via push from appliance"""

    # https://developers.home-assistant.io/docs/core/entity#subscribing-to-updates
    should_poll = False

    async def receive(self):
        """
        Called when data has been received by push from appliance
        """

        # Whenever you receive a new state from your subscription, you can tell Home Assistant
        # that an update is available by calling  async_schedule_update_ha_state().
        #
        # Pass in the boolean True to the method if you want Home Assistant
        # to call your update method before writing the update to Home Assistant.
        self.async_schedule_update_ha_state()


class CoordinatedEntity(Entity):
    """Receives its data from DataUpdateCoordinator"""

    should_poll = False


class Device:
    """

    An Ecobee thermostat with 4 room sensors equals 5 devices.

    https://developers.home-assistant.io/docs/device_registry_index#what-is-a-device
    https://developers.home-assistant.io/docs/device_registry_index#device-properties
    """
    entities: Entity = []

    # https://developers.home-assistant.io/docs/device_registry_index/#device-properties
    # TODO make a type for this dict
    device_info: dict|None = None


class PhysicalDevice(Device):
    """
    https://developers.home-assistant.io/docs/device_registry_index#what-is-a-device
    """


class ServiceDevice(Device):
    """
    https://developers.home-assistant.io/docs/device_registry_index#what-is-a-device
    """


class Appliance:
    """Highest level of physical device or service.

    Credentials used to connect to a controller are stored on this level.
    The ConfigEntry passed into an integrations __init__.py can be thought
    of as configuration for the Appliance.

    Example: An Ecobee thermostat with 4 room sensors equals 1 appliance.
    """

    devices: Device[] = []
