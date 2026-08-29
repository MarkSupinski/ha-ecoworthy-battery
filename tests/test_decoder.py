"""Unit tests for the ECOWORTHY BLE frame decoder (no HA / no BLE needed).

decoder.py is loaded directly because importing the package runs __init__.py,
which imports `homeassistant` (available on the target, not here).
"""

import importlib.util
from pathlib import Path

_DECODER_PATH = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "ecoworthy_battery"
    / "decoder.py"
)
_spec = importlib.util.spec_from_file_location("ecoworthy_decoder", _DECODER_PATH)
assert _spec and _spec.loader
decoder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(decoder)

# Frame captured from the user's ECO-WORTHY 314 Ah battery (0xA1 = pack data).
USER_A1_FRAME = bytes.fromhex(
    "c1060d2b3baea100000803440008001d00640527000000007aa8000100010000"
    "000000000000000000000000ffff00000000000000000000000300007aa80000"
    "00000000000000000000000000000000d623"
)

# Frames captured live from an ECO-WORTHY 0B_7AD5 battery.
LIVE_A1_FRAME = bytes.fromhex(
    "c1060d2f5433a100000803440008001c00640526000000007aa8000100010000"
    "000000000000000000000000ffff00000000000000000000000300007aa80000"
    "000000000000000000000000000000003365"
)
LIVE_A2_FRAME = bytes.fromhex(
    "c1060d2f5433a2000008035600040ce20ce00ce10ce3ffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffff0003010101060106fc18fc18fc18fc18fc18"
    "fc183ec5"
)


def test_crc16_modbus():
    assert decoder.crc16_modbus(USER_A1_FRAME[:-2]) == int.from_bytes(
        USER_A1_FRAME[-2:], "little"
    )
    assert decoder.is_valid_frame(USER_A1_FRAME)
    assert decoder.is_valid_frame(LIVE_A1_FRAME)
    assert decoder.is_valid_frame(LIVE_A2_FRAME)

    bad = bytearray(USER_A1_FRAME)
    bad[20] ^= 0xFF
    assert not decoder.is_valid_frame(bytes(bad))
    assert not decoder.is_valid_frame(b"\xdd\x03\x00\x00\xe0\x77")


def test_decode_main_user_frame():
    """The user's captured frame matches the values reported by the iOS app."""
    result = decoder.decode_main(USER_A1_FRAME)
    assert result["soc_pct"] == 29          # app shows 29% SOC
    assert result["soh_pct"] == 100
    assert result["voltage_v"] == 13.19     # app shows 13.19 V
    assert result["current_a"] == 0.0
    assert result["design_capacity_ah"] == 314.0
    assert result["problem_code"] == 0


def test_decode_main_live_frame():
    result = decoder.decode_main(LIVE_A1_FRAME)
    assert result["soc_pct"] == 28
    assert result["soh_pct"] == 100
    assert result["voltage_v"] == 13.18
    assert result["current_a"] == 0.0
    assert result["design_capacity_ah"] == 314.0


def test_decode_cells_live_frame():
    result = decoder.decode_cells(LIVE_A2_FRAME)
    assert result["cell_count"] == 4
    assert result["cells_v"] == [3.298, 3.296, 3.297, 3.299]
    assert abs(sum(result["cells_v"]) - 13.19) < 0.02
    assert result["temp_count"] == 3
    assert result["temps_c"] == [25.7, 26.2, 26.2]


def test_decode_frame_dispatch():
    assert decoder.decode_frame(USER_A1_FRAME) is not None
    assert decoder.decode_frame(LIVE_A1_FRAME)["voltage_v"] == 13.18
    assert decoder.decode_frame(LIVE_A2_FRAME)["cell_count"] == 4
    assert decoder.decode_frame(b"\x01\x02\x03") is None
