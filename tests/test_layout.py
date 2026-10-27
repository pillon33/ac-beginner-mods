"""pitwall_core/layout.py is generated from the ctypes structs in
telemetry/shared_memory.py, the single source of truth for AC's memory
layout. These tests fail when it's stale, and check the in-game reader
decodes bytes exactly like ctypes does."""

import struct
import sys

import pytest

from pitwall_core import layout
from pitwall_core.memory import read_field


def test_read_field_decodes_numbers_arrays_and_text():
    buffer = bytearray(64)
    struct.pack_into("<f", buffer, 12, 51.75)
    struct.pack_into("<i", buffer, 4, 25)
    struct.pack_into("<3f", buffer, 16, 1.0, 2.0, 3.0)
    buffer[32:32 + 10] = "spa".encode("utf-16-le") + b"\x00" * 4
    assert read_field(buffer, (12, "f")) == pytest.approx(51.75)
    assert read_field(buffer, (4, "i")) == 25
    assert read_field(buffer, (16, "3f")) == (1.0, 2.0, 3.0)
    assert read_field(buffer, (32, "10s")) == "spa"


windows_only = pytest.mark.skipif(
    sys.platform != "win32",
    reason="shared_memory.py is Windows-only (and c_wchar is 2 bytes only there)")


@windows_only
def test_generated_layout_is_up_to_date():
    import gen_layout

    with open(gen_layout.LAYOUT_PATH, encoding="utf-8") as current:
        assert current.read() == gen_layout.render(), \
            "pitwall_core/layout.py is stale: run python scripts/gen_layout.py"


@windows_only
def test_in_game_reader_matches_ctypes_on_the_same_bytes():
    from shared_memory import SPageFileGraphic, SPageFilePhysics, SPageFileStatic

    physics = SPageFilePhysics(fuel=48.87, gear=3, speedKmh=187.5)
    graphics = SPageFileGraphic(session=2, sessionTimeLeft=1234.5, numberOfLaps=25)
    static = SPageFileStatic(carModel="ks_audi_r8_lms", maxFuel=120.0, isTimedRace=1)

    assert read_field(bytes(physics), layout.PHYSICS["fuel"]) == pytest.approx(48.87, abs=1e-5)
    assert read_field(bytes(physics), layout.PHYSICS["gear"]) == 3
    assert read_field(bytes(graphics), layout.GRAPHICS["session"]) == 2
    assert read_field(bytes(graphics), layout.GRAPHICS["sessionTimeLeft"]) == pytest.approx(1234.5)
    assert read_field(bytes(graphics), layout.GRAPHICS["numberOfLaps"]) == 25
    assert read_field(bytes(static), layout.STATIC["carModel"]) == "ks_audi_r8_lms"
    assert read_field(bytes(static), layout.STATIC["maxFuel"]) == pytest.approx(120.0)
    assert read_field(bytes(static), layout.STATIC["isTimedRace"]) == 1
