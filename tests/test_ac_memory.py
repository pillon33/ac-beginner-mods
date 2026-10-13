"""The in-game reader (ac_memory.py) hard-codes byte offsets; the
external reader (telemetry/shared_memory.py) describes the same
structs with ctypes. They're two independent transcriptions of Kunos'
layout, so they must agree on where every field the HUD reads lives.
"""

import ctypes
import struct
import sys

import pytest

import ac_memory

if sys.platform != "win32":
    # shared_memory.py refuses to import elsewhere, and c_wchar is
    # 4 bytes on Linux/macOS, which would shift every offset anyway.
    pytest.skip("AC's shared memory layout is Windows-only", allow_module_level=True)

from shared_memory import SPageFileGraphic, SPageFilePhysics, SPageFileStatic  # noqa: E402


@pytest.mark.parametrize("offset, struct_type, field", [
    (ac_memory.PHYSICS_FUEL, SPageFilePhysics, "fuel"),
    (ac_memory.GRAPHICS_SESSION, SPageFileGraphic, "session"),
    (ac_memory.GRAPHICS_SESSION_TIME_LEFT, SPageFileGraphic, "sessionTimeLeft"),
    (ac_memory.GRAPHICS_NUMBER_OF_LAPS, SPageFileGraphic, "numberOfLaps"),
    (ac_memory.STATIC_IS_TIMED_RACE, SPageFileStatic, "isTimedRace"),
    (ac_memory.STATIC_HAS_EXTRA_LAP, SPageFileStatic, "hasExtraLap"),
])
def test_offset_matches_ctypes_struct(offset, struct_type, field):
    assert offset == getattr(struct_type, field).offset


def test_read_sizes_stay_inside_the_structs():
    assert ac_memory.PHYSICS_READ_SIZE <= ctypes.sizeof(SPageFilePhysics)
    assert ac_memory.GRAPHICS_READ_SIZE <= ctypes.sizeof(SPageFileGraphic)
    assert ac_memory.STATIC_READ_SIZE <= ctypes.sizeof(SPageFileStatic)


def test_reads_little_endian_values_at_an_offset():
    buffer = bytearray(16)
    struct.pack_into("<f", buffer, 12, 51.75)
    struct.pack_into("<i", buffer, 4, 25)
    assert ac_memory.read_float(buffer, 12) == pytest.approx(51.75)
    assert ac_memory.read_int(buffer, 4) == 25


def test_reader_and_ctypes_struct_decode_the_same_bytes():
    graphics = SPageFileGraphic(session=2, sessionTimeLeft=1234.5, numberOfLaps=25)
    raw = bytes(graphics)
    assert ac_memory.read_int(raw, ac_memory.GRAPHICS_SESSION) == 2
    assert ac_memory.read_float(raw, ac_memory.GRAPHICS_SESSION_TIME_LEFT) == pytest.approx(1234.5)
    assert ac_memory.read_int(raw, ac_memory.GRAPHICS_NUMBER_OF_LAPS) == 25
