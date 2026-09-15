"""
shared_memory.py — read Assetto Corsa's live telemetry from a normal,
external Python process (not from inside the game).

WHY THIS EXISTS
-----------------
The in-game apps/python apps (see apps/python/hello_hud) run on AC's
bundled Python 3.3 with no pip and no outside network access. That's
fine for a HUD widget, but it's the wrong place to call an LLM API,
run text-to-speech, or use any modern library — which is exactly what
an "AI race engineer" needs to do.

AC solves this by mirroring its telemetry, every physics frame, into
three named blocks of shared memory (Windows memory-mapped files)
that ANY process on the same machine can open read-only. This module
opens them and unpacks the bytes into Python objects using `ctypes`.

This only works on Windows (AC's shared memory uses the Windows
CreateFileMapping API under the hood, which is what Python's `mmap`
module exposes via its `tagname` argument — that argument doesn't
exist on Linux/macOS).

ACCURACY WARNING — READ THIS BEFORE YOU TRUST THE VALUES
-----------------------------------------------------------
ctypes.Structure parses this data by raw byte offset: field order,
field type, and array lengths all have to match Kunos' C struct
EXACTLY, or every field after the first mistake will silently read
garbage (not an error — just wrong numbers, NaNs, or garbled text).

The field layout below covers the common, stable, well-published
subset of each struct (speed/gear/rpm from physics; lap/session state
from graphics) that's been consistent across the AC modding community
for years. Kunos ships the authoritative reference with the game
itself:

    <AC install dir>\\sdk\\dev\\shared memory\\

Before you extend this file with more fields (tyre temps, damage,
etc.), open that reference and cross-check names, types and order.
A good sanity check once you're reading live data: the numbers should
look plausible (speed 0-350ish, gear -1..8) — if they look like noise,
you have a struct mismatch, and `ctypes.sizeof(SPageFilePhysics)`
should match the size AC's docs say the struct is.
"""

import ctypes
import mmap
import sys

if sys.platform != "win32":
    raise SystemExit(
        "shared_memory.py only works on Windows — AC's shared memory "
        "is a Windows-only mechanism (Python's mmap 'tagname' support "
        "is Windows-only too)."
    )


class SPageFilePhysics(ctypes.Structure):
    _fields_ = [
        ("packetId", ctypes.c_int32),
        ("gas", ctypes.c_float),
        ("brake", ctypes.c_float),
        ("fuel", ctypes.c_float),
        ("gear", ctypes.c_int32),          # 0 = reverse, 1 = neutral, 2+ = 1st, 2nd, ...
        ("rpms", ctypes.c_int32),
        ("steerAngle", ctypes.c_float),
        ("speedKmh", ctypes.c_float),
        ("velocity", ctypes.c_float * 3),
        ("accG", ctypes.c_float * 3),
        # Physics has many more fields after this point (tyre temps,
        # wear, suspension travel, damage...) — add them here once
        # you've checked them against the SDK reference above.
    ]


class SPageFileGraphic(ctypes.Structure):
    _fields_ = [
        ("packetId", ctypes.c_int32),
        ("status", ctypes.c_int32),        # AC_STATUS enum: 0 off, 1 replay, 2 live, 3 pause
        ("session", ctypes.c_int32),       # AC_SESSION_TYPE enum: practice/qualify/race/...
        ("currentTime", ctypes.c_wchar * 15),
        ("lastTime", ctypes.c_wchar * 15),
        ("bestTime", ctypes.c_wchar * 15),
        ("split", ctypes.c_wchar * 15),
        ("completedLaps", ctypes.c_int32),
        ("position", ctypes.c_int32),
        ("iCurrentTime", ctypes.c_int32),  # current lap time, milliseconds
        ("iLastTime", ctypes.c_int32),
        ("iBestTime", ctypes.c_int32),
        # Graphics has many more fields after this point (fuel
        # warnings, flags, tyre compound...) — same rule: verify
        # against the SDK reference before adding them.
    ]


AC_STATUS = {0: "OFF", 1: "REPLAY", 2: "LIVE", 3: "PAUSE"}
AC_SESSION_TYPE = {
    -1: "UNKNOWN", 0: "PRACTICE", 1: "QUALIFY", 2: "RACE",
    3: "HOTLAP", 4: "TIME_ATTACK", 5: "DRIFT", 6: "DRAG",
}


class ACTelemetry:
    """Opens AC's physics + graphics shared memory blocks and exposes
    their current values. Use as a context manager so the memory maps
    always get closed:

        with ACTelemetry() as ac_telemetry:
            physics, graphics = ac_telemetry.read()
    """

    def __init__(self):
        self._physics_mm = mmap.mmap(
            -1, ctypes.sizeof(SPageFilePhysics),
            tagname="Local\\acpmf_physics", access=mmap.ACCESS_READ,
        )
        self._graphics_mm = mmap.mmap(
            -1, ctypes.sizeof(SPageFileGraphic),
            tagname="Local\\acpmf_graphics", access=mmap.ACCESS_READ,
        )

    def read(self):
        physics = SPageFilePhysics.from_buffer_copy(self._physics_mm)
        graphics = SPageFileGraphic.from_buffer_copy(self._graphics_mm)
        return physics, graphics

    def close(self):
        self._physics_mm.close()
        self._graphics_mm.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
