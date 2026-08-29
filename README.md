# ECOWORTHY 0B Battery

Home Assistant integration for **ECOWORTHY 314 Ah LiFePO4 batteries** (the
`ECO-WORTHY 0B_xxxx` / `02_xxxx` series with built-in Bluetooth). It reads live
telemetry straight from the battery's BMS over BLE and exposes it as sensors.

## Features

- Auto-discovers every ECO-WORTHY / DCHOUSE battery in range of the Home
  Assistant Bluetooth adapter (Yellow's built-in radio, a USB dongle, or an
  ESPHome Bluetooth proxy all work — anything the HA `bluetooth` integration
  manages).
- Exposes per battery: **State of charge, Voltage, Current, Power,
  Temperature, Design capacity, State of health, Problem code** and
  **per-cell voltages** (Cell 1 … N).
- Polls every **60 seconds** by default (configurable in Options).
- Uses the custom BLE protocol reverse-engineered for these batteries
  (service `0xfff0`, frames `0xA1`/`0xA2`, Modbus-CRC validated).

## Install (HACS)

1. In HACS → **… → Custom repositories**, add this repository URL with category
   **Integration**.
2. Install **ECOWORTHY 0B Battery (BLE)**.
3. Restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → ECOWORTHY 0B Battery**.
5. Batteries are discovered automatically — no MAC addresses to enter.

The integration requires the Home Assistant **Bluetooth** integration (core)
to be set up with at least one adapter. On Home Assistant Yellow this is
built in; with a generic USB dongle make sure it is recognised and enabled
under Settings → Devices & Services → Bluetooth.

## Manual install

Copy the `custom_components/ecoworthy_battery` directory into your Home
Assistant `config/custom_components/` folder, restart, then add the
integration.

## Sensors created per battery

| Sensor | Unit | Notes |
|---|---|---|
| State of charge | % | |
| Voltage | V | |
| Current | A | signed; + charge / − discharge |
| Power | W | |
| Temperature | °C | first BMS temperature probe |
| Design capacity | Ah | 314 Ah on this model |
| State of health | % | |
| Problem code | | 0 = no fault |
| Cell 1 … N voltage | V | one sensor per cell |

## Configuration options

Under **Options** you can change the BLE poll interval (30–3600 s, default 60).

## Troubleshooting

- **No batteries found** — check the Bluetooth integration sees the battery
  (`Settings → Devices & Services → Bluetooth`), and that the battery is awake
  (tap it / recently used). Batteries advertise as `ECO-WORTHY 0B_xxxx`.
- **Battery shows unavailable** — the battery was not connectable during the
  last poll (sleeping, out of range, or another client connected). It recovers
  automatically on the next poll.
- **Card says "X minutes ago" / stale timestamp** — the card may be showing the
  sensor's *last changed* time, which stays frozen while the SOC value is
  unchanged (normal for an idle battery). Use the **`Last update`** sensor
  (device_class timestamp) to see when the integration last *read* the battery;
  it advances every poll. If *that* is also stale, the battery is sleeping or
  out of range — wake it or check the Bluetooth integration.
- **Only some cells reported** — the 0xA2 frame includes a cell count; a
  sensor is created per reported cell.

## Credits

Protocol reverse-engineering cross-checked against the `aiobmsble` ECO-WORTHY
driver and validated with captured frames from a live ECO-WORTHY 314 Ah pack.
