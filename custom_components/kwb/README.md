# KWB Easyfire

Initially copied from the [official Home Assistant integration](https://github.com/home-assistant/core/tree/dev/homeassistant/components/kwb).

## GUI setup

After installing the custom integration, restart Home Assistant. Open **Settings → Devices & services → Add integration → KWB Easyfire**.

1. Enter a heater name and select **Serial** or **TCP**. Enter the heater's positive **Nominal heater power (kW)** rating (default: **25 kW**). Set **Pellet Bulk Density (kg/L)** to the mass of one liter of loose pellets, including the spaces between pellets (default: **0.65 kg/L**, must be positive).
2. For serial, enter the device path (for example, `/dev/ttyUSB0`, or preferably a persistent `/dev/serial/by-id/` path).
3. For TCP, enter the serial server's host and port (default: `23`).
4. Leave **Include raw packet sensors** unchecked for normal operation, then submit.

Setup checks whether the connection can be opened. It does not verify that the connected device is a KWB controller. Decoded sensors become available as pykwb receives packets. The heater name is used for the device, integration entry, and sensor names. Configuring the same endpoint again is prevented.

The setup dialog is opened through **Add integration**; installing files through HACS does not automatically open it. Existing YAML sensor configurations remain supported. Remove a heater's YAML configuration and restart before adding that same heater through the GUI to avoid duplicate connections.

With a nominal rating configured and a pykwb version that exposes **Heater Output**, **Heater Power Output** reports `nominal_power × (heater_output / 100)` in kW. For example, a 25 kW heater at 40% output reports 10 kW. It follows the source reading’s availability. The entity ID follows the usual naming convention: `sensor.{name}_heater_power_output`.

**Heater Energy Output** accumulates **Heater Power Output** into kWh using Home Assistant's built-in [Integral sensor](https://www.home-assistant.io/integrations/integration/). It uses the left Riemann sum (the last reported power applies until the next reading) and updates at least once per minute while power is available, even when power is constant. The accumulated total is restored after a Home Assistant restart; unavailable periods are not counted. For example, 12 kW for 30 minutes adds 6 kWh. Both sensors are created when nominal power is configured and the heater output reading is supported. The energy entity ID normally follows `sensor.{name}_heater_energy_output`.

## Resetting heater energy output

The heater device includes **Reset <Heater name> Heater Energy Output**.
Press it on the device page, add it to a dashboard, or invoke `button.press`.
It resets the running total to 0 kWh and starts accumulating from that moment.
The reset total and statistics reset timestamp survive normal restarts. Recorded
history is retained. The button is created automatically when heater energy output
is supported, including after reloading an existing installation. The energy
sensor must be enabled and loaded for the button to work.

The **Reset <Heater name> Pellet Consumption** button similarly resets the
accumulated pellet mass to **0 kg** and resumes counting from that moment.
It is added when the Pellet Consumption sensor is supported. The total must be
enabled and loaded. Resetting pellet consumption does not reset heater energy,
change pellet properties, or delete history. The zero total survives normal restarts.

## Editable calculation settings

Nominal heater power (kW), boiler efficiency (%), pellet bulk density (kg/L),
pellet energy density (kWh/kg), and pellet price (configured currency per metric ton)
are editable number entities under the
heater device's configuration controls. Entity names include the heater name.
These local calculation settings remain available when the boiler is disconnected;
editing them does not send commands to the boiler. Changes are saved in the
integration's options and immediately update the calculated power and pellet rates.

New setup always starts with defaults of **25 kW**, **95%**, **0.65 kg/L**, and
**4.8 kWh/kg**, plus a pellet price of **0 per metric ton**, including after removing and re-adding the integration. Existing
saved settings take precedence; missing settings in older entries receive defaults.
The previous read-only property sensors are replaced with number entities, so
cards or automations referring to those old sensor IDs need updating.

## Pellet consumption estimates

Review **Boiler efficiency (%)** (default **95%**) and **Pellet energy density (kWh/kg)**
(default **4.8 kWh/kg**) during setup,
along with nominal heater power, to create three additional sensors:

- **Pellet Consumption Rate** (`kg/h`): thermal output in kW divided by
  `(efficiency / 100) × pellet energy`.
- **Pellet Volume Flow Rate** (`L/h`): consumption in kg/h divided by
  **Pellet Bulk Density (kg/L)** (default `0.65`). This sensor uses the
  `volume_flow_rate` device class and can be selected in the Energy dashboard's
  **Gas flow rate** field.

- **Pellet Consumption** (`kg`): cumulative estimated mass since installation,
  using the `weight` device class and `total_increasing` state class. Integrates
  the consumption rate using the left method, updating at least every minute
  while readings are valid. Starts at zero and restores its total after Home
  Assistant restarts, with no automatic resets. Unavailable intervals and Home
  Assistant downtime are not backfilled. Calculation setting changes affect
  future consumption only. Displays two decimals and retains greater precision.

The two rate sensors use the `measurement` state class. For example, 15 kW at 90%
efficiency with 4.8 kWh/kg pellets and 0.65 kg/L bulk density yields about
3.47 kg/h and 5.34 L/h. They follow heater-output availability, report zero
for valid zero output, and return unknown for invalid readings. These are
estimates from output percentage and fixed fuel properties; ignition and
shutdown consumption may differ. Efficiency and pellet energy must use the
same heating-value basis. Missing properties in older entries are initialized with the setup defaults.

## Listener

The integration runs pykwb’s `listen_forever()` in a shared Home Assistant
background task. pykwb owns connection creation, cleanup, and TCP reconnection.
TCP reconnection is enabled for normal operation, using pykwb’s defaults:
a 5-second connection timeout, a 30-second valid-packet timeout, and exponential
retry delays from 1 to 30 seconds. pykwb marks readings unavailable on connection
loss and resumes updates after reconnecting. The config-flow connection probe
disables retries so a failed connection is reported to the user.

Connection creation runs in Home Assistant’s executor. Unload and shutdown cancel
the listener and ask pykwb to close the connection. This requires the local
pykwb development version with async reconnection support; the pinned release
does not provide this API.

## Translations

UI text lives in `strings.json` and `translations/en.json`, including the connection selector labels. Add other languages as `translations/<language>.json` with the same keys.

## Checks

From the repository root, with the development dependencies and the local pykwb checkout:

```sh
PYTHONPATH=../pykwb python -m unittest discover -s tests -v
python -m ruff check custom_components/kwb tests/test_kwb.py
python -m mypy custom_components/kwb
```

## Pellet consumption cost

Set **Pellet price (per metric ton)** during setup or edit **Pellet price** on
the heater device later. The default is 0; enter your supplier's price for
1 metric ton (1,000 kg) in Home Assistant's configured currency. Zero and positive
prices are accepted. The number entity displays a unit such as `EUR/t`.

**<Heater name> Pellet Consumption Cost** reports
`Pellet Consumption (kg) / 1000 × Pellet price` in that currency.
For example, 250 kg at 400 EUR/t costs 100 EUR. The cost updates with consumption,
price changes, and consumption resets. Resetting Pellet Consumption also resets
its cost to zero. Changing the price revalues the entire current consumption total;
this is not a historical ledger of purchases at different prices. The cost sensor
therefore has no total state class for Energy dashboard expenditure statistics.
