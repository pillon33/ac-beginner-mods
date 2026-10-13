"""
ac_memory.py — read single fields from AC's shared memory inside the
game, without ctypes.

AC's embedded Python ships no _ctypes.pyd, but `mmap` and `struct`
are built into its python33.dll. Each value the HUD needs sits at a
fixed byte offset in Kunos' structs, so `struct.unpack_from` at that
offset is all it takes.

The offsets below must match the ctypes structs in
telemetry/shared_memory.py. tests/test_ac_memory.py checks that they
do, so a typo here fails a test instead of silently showing garbage.

Python 3.3: no f-strings (see CLAUDE.md).
"""

import mmap
import struct

PHYSICS_TAG = "Local\\acpmf_physics"
GRAPHICS_TAG = "Local\\acpmf_graphics"
STATIC_TAG = "Local\\acpmf_static"

# SPageFilePhysics
PHYSICS_FUEL = 12                 # float, litres

# SPageFileGraphic
GRAPHICS_SESSION = 8              # int32, AC_SESSION_TYPE
GRAPHICS_SESSION_TIME_LEFT = 152  # float, milliseconds
GRAPHICS_NUMBER_OF_LAPS = 172     # int32, race length (lap races)

# SPageFileStatic
STATIC_IS_TIMED_RACE = 596        # int32, bool
STATIC_HAS_EXTRA_LAP = 600        # int32, bool

# Map only as much of each block as we read: up to the last field.
PHYSICS_READ_SIZE = PHYSICS_FUEL + 4
GRAPHICS_READ_SIZE = GRAPHICS_NUMBER_OF_LAPS + 4
STATIC_READ_SIZE = STATIC_HAS_EXTRA_LAP + 4


def read_float(buffer, offset):
    return struct.unpack_from("<f", buffer, offset)[0]


def read_int(buffer, offset):
    return struct.unpack_from("<i", buffer, offset)[0]


class SharedMemoryBlock(object):
    """A read-only view of one of AC's shared memory blocks."""

    def __init__(self, tag, size):
        self._map = mmap.mmap(-1, size, tagname=tag, access=mmap.ACCESS_READ)

    def float_at(self, offset):
        return read_float(self._map, offset)

    def int_at(self, offset):
        return read_int(self._map, offset)

    def close(self):
        self._map.close()
