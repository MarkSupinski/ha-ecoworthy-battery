"""BLE discovery + polling coordinator for ECOWORTHY batteries."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
    async_register_callback,
    async_ble_device_from_address,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from bleak import BleakClient

from . import decoder
from .const import (
    CHAR_NOTIFY,
    CHAR_WRITE,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FRAME_COLLECT_TIMEOUT,
    FRAME_WAIT_AFTER_WRITE,
    INIT_COMMANDS,
    NAME_PREFIXES,
)

_LOGGER = logging.getLogger(__name__)


def _is_ecoworthy(service_info: BluetoothServiceInfoBleak) -> bool:
    """Return True if the advertised device belongs to the ECOWORTHY family."""
    name = (service_info.name or "").upper()
    return any(name.startswith(prefix.upper()) for prefix in NAME_PREFIXES)


def _has_frame_pair(frames: list[bytes]) -> bool:
    """Return True when a valid 0xA1 and 0xA2 frame pair was captured."""
    kinds = {
        f[decoder.PREFIX_LEN]
        for f in frames
        if decoder.is_valid_frame(f)
    }
    return decoder.COMMAND_MAIN in kinds and decoder.COMMAND_CELLS in kinds


@dataclass
class BatteryData:
    """Decoded telemetry for a single battery snapshot."""

    address: str
    name: str
    soc: float | None = None
    voltage: float | None = None
    current: float | None = None
    power: float | None = None
    temperature: float | None = None
    capacity_ah: float | None = None
    soh: float | None = None
    problem_code: int | None = None
    cells: list[float] = field(default_factory=list)
    last_updated: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @classmethod
    def from_frames(
        cls,
        address: str,
        name: str,
        main: dict[str, Any],
        cells: dict[str, Any] | None,
    ) -> "BatteryData":
        voltage = main.get("voltage_v")
        current = main.get("current_a")
        temps = cells.get("temps_c") if cells else []
        power = None
        if voltage is not None and current is not None:
            power = round(voltage * current, 2)
        return cls(
            address=address,
            name=name,
            soc=main.get("soc_pct"),
            voltage=voltage,
            current=current,
            power=power,
            temperature=temps[0] if temps else None,
            capacity_ah=main.get("design_capacity_ah"),
            soh=main.get("soh_pct"),
            problem_code=main.get("problem_code"),
            cells=cells.get("cells_v") if cells else [],
        )


class ECOWORTHYBatteryCoordinator(DataUpdateCoordinator[dict[str, BatteryData | None]]):
    """Poll all discovered ECOWORTHY batteries over BLE every scan interval."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._discovered: dict[str, str] = {}  # address -> device name
        self._reported_addresses: set[str] = set()  # addresses with a good read
        self._reported_cells: dict[str, int] = {}  # address -> last cell count
        self._first_update = True
        self._unregister_callbacks: list[Any] = []
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=config_entry.options.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                )
            ),
        )

    @property
    def discovered_batteries(self) -> dict[str, str]:
        """Address -> name for every battery ever seen (even if unreadable)."""
        return dict(self._discovered)

    async def _async_setup(self) -> None:
        """Register for BLE advertisements and pick up already-seen devices."""
        self._unregister_callbacks.append(
            async_register_callback(
                self.hass,
                self._handle_bluetooth_event,
                {},  # match everything; filter by name below
                BluetoothScanningMode.ACTIVE,
            )
        )
        for info in async_discovered_service_info(self.hass):
            if _is_ecoworthy(info):
                self._discovered.setdefault(info.address, info.name or info.address)

    async def async_unload(self) -> None:
        for unregister in self._unregister_callbacks:
            unregister()
        self._unregister_callbacks.clear()
        await self.async_shutdown()

    def _handle_bluetooth_event(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        if change == BluetoothChange.REMOVED:
            return
        if not _is_ecoworthy(service_info):
            return
        if service_info.address in self._discovered:
            return
        self._discovered[service_info.address] = service_info.name or service_info.address
        _LOGGER.info(
            "Discovered ECOWORTHY battery %s (%s); reloading to create entities",
            service_info.name,
            service_info.address,
        )
        # New device -> recreate sensor entities.
        self.hass.config_entries.async_schedule_reload(self._config_entry.entry_id)

    async def _async_update_data(self) -> dict[str, BatteryData | None]:
        """Connect to every known battery and collect fresh telemetry."""
        for info in async_discovered_service_info(self.hass):
            if _is_ecoworthy(info):
                self._discovered.setdefault(info.address, info.name or info.address)

        if not self._discovered:
            _LOGGER.debug("No ECOWORTHY batteries advertised")
            return {}

        data: dict[str, BatteryData | None] = {}
        for address in sorted(self._discovered):
            data[address] = await self._read_battery(address)

        _LOGGER.debug(
            "ECOWORTHY poll: discovered=%s read_ok=%s",
            sorted(self._discovered),
            sorted(
                reading.address
                for reading in data.values()
                if reading is not None
            ),
        )

        # Track which batteries report data and how many cells each has, so we
        # can reload and create entities the first time a battery becomes
        # readable (or grows its cell count) without spamming reloads.
        successful = {
            address for address, reading in data.items() if reading is not None
        }
        reload_reason: str | None = None
        if self._first_update:
            self._first_update = False
            self._reported_addresses = set(successful)
            for address in successful:
                self._reported_cells.setdefault(address, len(data[address].cells))
        else:
            new_readings = successful - self._reported_addresses
            if new_readings:
                self._reported_addresses |= new_readings
                reload_reason = (
                    "new batteries read successfully: "
                    + ", ".join(sorted(new_readings))
                )
            for address in successful:
                cell_count = len(data[address].cells)
                if cell_count > self._reported_cells.get(address, 0):
                    self._reported_cells[address] = cell_count
                    reload_reason = f"cell count for {address} grew to {cell_count}"

        if reload_reason:
            _LOGGER.info("Reloading to create entities (%s)", reload_reason)
            self.hass.config_entries.async_schedule_reload(self._config_entry.entry_id)

        return data

    async def _read_battery(self, address: str) -> BatteryData | None:
        """Connect to one battery and read its telemetry frames.

        Wrapped in a timeout so a stalled BLE connection can never hang the
        whole poll cycle.
        """
        device = async_ble_device_from_address(
            self.hass, address, connectable=True
        )
        if device is None:
            _LOGGER.debug("Battery %s is not connectable right now", address)
            return None
        name = self._discovered.get(address, device.name or address)
        try:
            return await asyncio.wait_for(
                self._read_battery_once(device, name, address), timeout=READ_TIMEOUT
            )
        except asyncio.TimeoutError:
            _LOGGER.warning("Timed out reading battery %s", name)
            return None
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Failed to read battery %s: %s", name, err)
            return None

    async def _read_battery_once(self, device, name: str, address: str) -> BatteryData | None:
        """Perform a single GATT read cycle against one battery."""
        async with BleakClient(device) as client:
            frames: list[bytes] = []

            def _handler(_uuid: str, data: bytearray) -> None:
                frames.append(bytes(data))

            await client.start_notify(CHAR_NOTIFY, _handler)

            # Send the init commands that trigger the telemetry stream.
            for cmd in INIT_COMMANDS:
                try:
                    await client.write_gatt_char(CHAR_WRITE, cmd, response=True)
                except Exception:  # noqa: BLE001 - some modules only accept 0x52
                    try:
                        await client.write_gatt_char(CHAR_WRITE, cmd, response=False)
                    except Exception as exc:  # noqa: BLE001
                        _LOGGER.debug("init write %s failed: %s", cmd.hex(), exc)
                await asyncio.sleep(FRAME_WAIT_AFTER_WRITE)
                if _has_frame_pair(frames):
                    break

            # Collect until we have both frame types or we time out.
            loop = asyncio.get_running_loop()
            deadline = loop.time() + FRAME_COLLECT_TIMEOUT
            while not _has_frame_pair(frames) and loop.time() < deadline:
                await asyncio.sleep(0.5)

            try:
                await client.stop_notify(CHAR_NOTIFY)
            except Exception:  # noqa: BLE001
                pass

        main: dict[str, Any] | None = None
        cells: dict[str, Any] | None = None
        for frame in frames:
            decoded = decoder.decode_frame(frame)
            if decoded is None:
                continue
            if frame[decoder.PREFIX_LEN] == decoder.COMMAND_MAIN:
                main = decoded
            else:
                cells = decoded

        if main is None and cells is None:
            _LOGGER.warning("No telemetry received from %s", name)
            return None

        reading = BatteryData.from_frames(address, name, main or {}, cells)
        _LOGGER.debug(
            "Read %s: %.2f V, %.1f%% SOC, %d cells",
            name, reading.voltage or 0, reading.soc or 0, len(reading.cells),
        )
        return reading
