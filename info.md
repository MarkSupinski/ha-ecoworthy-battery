# ECOWORTHY 0B Battery (BLE)

Home Assistant integration for ECOWORTHY 314 Ah LiFePO4 batteries
(`ECO-WORTHY 0B_xxxx` / `02_xxxx`).

Reads SOC, voltage, current, power, temperature, capacity, state of health,
problem code and per-cell voltages over Bluetooth every 60 s (configurable).

Auto-discovers batteries via the Home Assistant Bluetooth integration — works
with the Yellow's built-in radio, a USB dongle, or an ESPHome proxy.

Install via HACS → Custom repositories → this URL (category: Integration).
