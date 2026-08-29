"""Constants for the ECOWORTHY battery integration."""

DOMAIN = "ecoworthy_battery"
TITLE = "ECOWORTHY Battery"

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 60  # seconds

# Advertised device names for the ECO-WORTHY / DCHOUSE battery family.
NAME_PREFIXES = ("ECO-WORTHY", "DCHOUSE")

# BLE GATT layout: single service 0xfff0, notify on 0xfff1, write on 0xfff2.
SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
CHAR_NOTIFY = "0000fff1-0000-1000-8000-00805f9b34fb"
CHAR_WRITE = "0000fff2-0000-1000-8000-00805f9b34fb"

# Writing either init command makes the module stream telemetry on 0xfff1.
INIT_COMMANDS = (
    bytes.fromhex("ff0802000b01006401ffffffffffffff002d"),
    bytes.fromhex("ff0802000b01001401ffffffffffffff65ef"),
)

# How long to collect telemetry frames after the init write.
FRAME_COLLECT_TIMEOUT = 8.0
# How long to wait between the init write and the first frame.
FRAME_WAIT_AFTER_WRITE = 1.0
# Upper bound for one full battery read (connect + frames), so a stalled
# BLE connection can never hang the whole poll cycle.
READ_TIMEOUT = 25.0

MANUFACTURER = "ECOWORTHY"
MODEL = "314 Ah LiFePO4 (0B/02)"
