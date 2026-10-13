"""
memory.py — read fields from AC's shared memory by name, using only
`mmap` and `struct` (AC's embedded Python has no ctypes).

Offsets and formats come from layout.py, which is generated from the
ctypes structs in telemetry/shared_memory.py.

    memory = SharedMemory()
    memory.physics.get("fuel")
    memory.static.get("carModel")
"""

import mmap
import struct

from pitwall_core import layout


def read_field(buffer, field):
    """Decode one (offset, format) field from `buffer`: a number, a
    tuple for arrays, or a str for UTF-16 text."""
    offset, fmt = field
    values = struct.unpack_from("<" + fmt, buffer, offset)
    if fmt.endswith("s"):
        return values[0].decode("utf-16-le").split("\x00", 1)[0]
    if len(values) == 1:
        return values[0]
    return values


class MemoryBlock(object):
    """A read-only view of one shared memory block."""

    def __init__(self, tag, size, fields):
        self._map = mmap.mmap(-1, size, tagname=tag, access=mmap.ACCESS_READ)
        self._fields = fields

    def get(self, name):
        return read_field(self._map, self._fields[name])

    def close(self):
        self._map.close()


class SharedMemory(object):
    """AC's three shared memory blocks: physics, graphics and static."""

    def __init__(self):
        self.physics = MemoryBlock(layout.PHYSICS_TAG, layout.PHYSICS_SIZE, layout.PHYSICS)
        self.graphics = MemoryBlock(layout.GRAPHICS_TAG, layout.GRAPHICS_SIZE, layout.GRAPHICS)
        self.static = MemoryBlock(layout.STATIC_TAG, layout.STATIC_SIZE, layout.STATIC)

    def close(self):
        for block in (self.physics, self.graphics, self.static):
            block.close()
