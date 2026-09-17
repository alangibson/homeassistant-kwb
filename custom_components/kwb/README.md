# KWB Easyfire

Initially copied from the [official Home Assistant integration](https://github.com/home-assistant/core/tree/dev/homeassistant/components/kwb).

## GUI setup

After installing the custom integration, restart Home Assistant. Open **Settings → Devices & services → Add integration → KWB Easyfire**.

1. Enter a heater name and select **Serial** or **TCP**. Optionally enter the heater's positive **Nominal heater power (kW)** rating.
2. For serial, enter the device path (for example, `/dev/ttyUSB0`, or preferably a persistent `/dev/serial/by-id/` path).
3. For TCP, enter the serial server's host and port (default: `23`).
4. Leave **Include raw packet sensors** unchecked for normal operation, then submit.

Setup checks whether the connection can be opened. It does not verify that the connected device is a KWB controller. Decoded sensors become available as pykwb receives packets. The heater name is used for the device, integration entry, and sensor names. Configuring the same endpoint again is prevented.

The setup dialog is opened through **Add integration**; installing files through HACS does not automatically open it. Existing YAML sensor configurations remain supported. Remove a heater's YAML configuration and restart before adding that same heater through the GUI to avoid duplicate connections.

With a nominal rating configured and a pykwb version that exposes **Heater Output**, **Heater Power Output** reports `nominal_power × (heater_output / 100)` in kW. For example, a 25 kW heater at 40% output reports 10 kW. It follows the source reading’s availability. The entity ID follows the usual naming convention: `sensor.{name}_heater_power_output`.

**Heater Energy Output** accumulates **Heater Power Output** into kWh using Home Assistant's built-in [Integral sensor](https://www.home-assistant.io/integrations/integration/). It uses the left Riemann sum (the last reported power applies until the next reading) and updates at least once per minute while power is available, even when power is constant. The accumulated total is restored after a Home Assistant restart; unavailable periods are not counted. For example, 12 kW for 30 minutes adds 6 kWh. Both sensors are created when nominal power is configured and the heater output reading is supported. The energy entity ID normally follows `sensor.{name}_heater_energy_output`.

## Listener

The integration uses a shared async task that repeatedly calls pykwb’s
`listen_for()` method. It requires the local development version of pykwb
with this API; the pinned release does not provide it. Connection creation
runs in Home Assistant’s executor. Unload and shutdown cancel the listener
and close the connection.

## Translations

UI text lives in `strings.json` and `translations/en.json`, including the connection selector labels. Add other languages as `translations/<language>.json` with the same keys.

## Checks

From the repository root, with the development dependencies and `pykwb==0.0.21` installed:

```sh
python -m unittest discover -s tests -v
python -m ruff check custom_components/kwb tests/test_kwb.py
python -m mypy custom_components/kwb
```
