"""
shared_memory.py — read Assetto Corsa's live telemetry from a normal,
external Python process (not from inside the game).

WHY THIS EXISTS
-----------------
The in-game app (apps/python/pitwall) runs on AC's
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

The field layout below covers a stable, widely published prefix of
each struct. It was transcribed from sim_info.py in
https://github.com/albertowd/live-telemetry (AC SDK 1.14.3); the Kunos
SDK reference folder (sdk\\dev\\shared memory) isn't shipped with every
install. Cross-check names, types and order against such a reference
before adding fields, then check the values look plausible live
(speed 0-350ish, gear -1..8). Noise means a mismatch.

SINGLE SOURCE OF TRUTH
-----------------------
These structs also define the layout the in-game app reads. The
in-game Python has no ctypes, so scripts/gen_layout.py turns them
into plain byte offsets in pitwall_core/layout.py. After changing a
struct, run:

    python scripts/gen_layout.py

tests/test_layout.py fails until the generated file matches.
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
        ("sessionTimeLeft", ctypes.c_float),  # milliseconds
        ("distanceTraveled", ctypes.c_float),  # metres, this session
        ("isInPit", ctypes.c_int32),
        ("currentSectorIndex", ctypes.c_int32),
        ("lastSectorTime", ctypes.c_int32),
        ("numberOfLaps", ctypes.c_int32),      # race length for lap races
        # Graphics has more fields after this point (tyre compound,
        # normalized car position, flags...) — same rule: verify
        # against the SDK reference before adding them.
    ]


class SPageFileStatic(ctypes.Structure):
    """Session constants: written once when a session loads."""
    _fields_ = [
        ("smVersion", ctypes.c_wchar * 15),
        ("acVersion", ctypes.c_wchar * 15),
        ("numberOfSessions", ctypes.c_int32),
        ("numCars", ctypes.c_int32),
        ("carModel", ctypes.c_wchar * 33),
        ("track", ctypes.c_wchar * 33),
        ("playerName", ctypes.c_wchar * 33),
        ("playerSurname", ctypes.c_wchar * 33),
        ("playerNick", ctypes.c_wchar * 33),
        ("sectorCount", ctypes.c_int32),
        ("maxTorque", ctypes.c_float),
        ("maxPower", ctypes.c_float),
        ("maxRpm", ctypes.c_int32),
        ("maxFuel", ctypes.c_float),               # tank capacity, litres
        ("suspensionMaxTravel", ctypes.c_float * 4),
        ("tyreRadius", ctypes.c_float * 4),
        ("maxTurboBoost", ctypes.c_float),
        ("airTemp", ctypes.c_float),
        ("roadTemp", ctypes.c_float),
        ("penaltiesEnabled", ctypes.c_int32),
        ("aidFuelRate", ctypes.c_float),           # fuel consumption multiplier, 0 = off
        ("aidTireRate", ctypes.c_float),
        ("aidMechanicalDamage", ctypes.c_float),
        ("aidAllowTyreBlankets", ctypes.c_int32),
        ("aidStability", ctypes.c_float),
        ("aidAutoClutch", ctypes.c_int32),
        ("aidAutoBlip", ctypes.c_int32),
        ("hasDRS", ctypes.c_int32),
        ("hasERS", ctypes.c_int32),
        ("hasKERS", ctypes.c_int32),
        ("kersMaxJ", ctypes.c_float),
        ("engineBrakeSettingsCount", ctypes.c_int32),
        ("ersPowerControllerCount", ctypes.c_int32),
        ("trackSPlineLength", ctypes.c_float),     # lap length, metres
        ("trackConfiguration", ctypes.c_wchar * 33),
        ("ersMaxJ", ctypes.c_float),
        ("isTimedRace", ctypes.c_int32),
        ("hasExtraLap", ctypes.c_int32),
        # Static has a few more fields after this point (car skin,
        # reversed grid, pit window) — verify before adding.
    ]


# (name, shared memory tag, struct) for each block AC publishes.
BLOCKS = (
    ("physics", "Local\\acpmf_physics", SPageFilePhysics),
    ("graphics", "Local\\acpmf_graphics", SPageFileGraphic),
    ("static", "Local\\acpmf_static", SPageFileStatic),
)

AC_STATUS = {0: "OFF", 1: "REPLAY", 2: "LIVE", 3: "PAUSE"}
AC_SESSION_TYPE = {
    -1: "UNKNOWN", 0: "PRACTICE", 1: "QUALIFY", 2: "RACE",
    3: "HOTLAP", 4: "TIME_ATTACK", 5: "DRIFT", 6: "DRAG",
}


class ACTelemetry:
    """Opens AC's physics, graphics and static shared memory blocks and
    exposes their current values. Use as a context manager so the
    memory maps always get closed:

        with ACTelemetry() as ac_telemetry:
            physics, graphics = ac_telemetry.read()
            static = ac_telemetry.read_static()   # once per session
    """

    def __init__(self):
        self._maps = {
            name: mmap.mmap(-1, ctypes.sizeof(struct), tagname=tag, access=mmap.ACCESS_READ)
            for name, tag, struct in BLOCKS
        }

    def read(self):
        physics = SPageFilePhysics.from_buffer_copy(self._maps["physics"])
        graphics = SPageFileGraphic.from_buffer_copy(self._maps["graphics"])
        return physics, graphics

    def read_static(self):
        return SPageFileStatic.from_buffer_copy(self._maps["static"])

    def close(self):
        for shared_map in self._maps.values():
            shared_map.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
