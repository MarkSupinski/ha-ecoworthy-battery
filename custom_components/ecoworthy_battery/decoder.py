"""Decoder for ECO-WORTHY '0B' / '02' family (BMS model 'BW 02/0B') BLE frames.

Pure Python, no Home Assistant dependencies — kept separate so it can be unit
tested against captured frames.

Frame format (notification on characteristic ``0xfff1``)::

    <6-byte session prefix> 0xA1 <73-byte payload> <crc16-modbus lo hi>
    <6-byte session prefix> 0xA2 <91-byte payload> <crc16-modbus lo hi>

The 6-byte prefix is a per-session device identifier. The trailing two bytes
are a little-endian Modbus CRC16 over the whole frame. All multi-byte fields
are big-endian. Field offsets match the aiobmsble ECO-WORTHY driver, which
reads them from a message built as two zero bytes followed by the raw frame.
"""

from __future__ import annotations

from typing import Any, Dict, List

COMMAND_MAIN = 0xA1  # voltage / current / SOC / SOH / capacity / problem code
COMMAND_CELLS = 0xA2  # per-cell voltages + temperatures
PREFIX_LEN = 6
HEADER_LEN = PREFIX_LEN + 1


def crc16_modbus(data: bytes) -> int:
    """Return CRC-16-MODBUS of *data* (poly 0xA001, init 0xFFFF)."""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def is_valid_frame(data: bytes) -> bool:
    """Return True if *data* is a CRC-valid ECO-WORTHY telemetry frame."""
    if len(data) < HEADER_LEN + 2:
        return False
    if data[PREFIX_LEN] not in (COMMAND_MAIN, COMMAND_CELLS):
        return False
    return crc16_modbus(data[:-2]) == int.from_bytes(data[-2:], "little")


def _msg(frame: bytes) -> bytes:
    """Build the message the field offsets are indexed against."""
    return b"\x00\x00" + frame


def decode_main(frame: bytes) -> Dict[str, Any]:
    """Decode an 0xA1 frame (pack-level telemetry)."""
    s = _msg(frame)
    # The 0xA1/0xA2 frames from this module carry a 6-byte session prefix, so
    # the "V2" field layout applies: current is in 10 mA units.
    current = int.from_bytes(s[22:24], "big", signed=True) / 10.0
    return {
        "soc_pct": int.from_bytes(s[16:18], "big"),
        "soh_pct": int.from_bytes(s[18:20], "big"),
        "voltage_v": round(int.from_bytes(s[20:22], "big") / 100.0, 2),
        "current_a": round(current, 2),
        "design_capacity_ah": round(int.from_bytes(s[26:28], "big") / 100.0, 2),
        "problem_code": int.from_bytes(s[51:53], "big"),
    }


def decode_cells(frame: bytes) -> Dict[str, Any]:
    """Decode an 0xA2 frame (per-cell voltages and temperatures)."""
    s = _msg(frame)
    cell_count = int.from_bytes(s[14:16], "big")
    cells: List[float] = []
    for i in range(cell_count):
        mv = int.from_bytes(s[16 + i * 2: 18 + i * 2], "big")
        cells.append(round(mv / 1000.0, 3))
    temp_count = int.from_bytes(s[80:82], "big")
    temps = [
        round(int.from_bytes(s[82 + i * 2: 84 + i * 2], "big", signed=True) / 10.0, 1)
        for i in range(temp_count)
    ]
    return {
        "cell_count": cell_count,
        "cells_v": cells,
        "temp_count": temp_count,
        "temps_c": temps,
    }


def decode_frame(frame: bytes) -> Dict[str, Any] | None:
    """Decode any valid ECO-WORTHY frame, or None if it isn't one."""
    if not is_valid_frame(frame):
        return None
    if frame[PREFIX_LEN] == COMMAND_MAIN:
        return decode_main(frame)
    return decode_cells(frame)
