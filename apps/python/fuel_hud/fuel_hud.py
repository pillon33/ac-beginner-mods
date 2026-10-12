"""
fuel_hud.py — in-game Assetto Corsa app showing fuel in the tank,
fuel used this lap, fuel used last lap, and the average per lap.

This file is the thin edge between the game and fuel_logic.py: it
reads the game every frame, hands the numbers to a FuelTracker, and
writes the results into labels. All the lap bookkeeping lives in
fuel_logic.py, where pytest can reach it.

WHERE THE FUEL NUMBER COMES FROM
---------------------------------
`ac.getCarState()` has no fuel entry (see the CS list in
<AC install>\\apps\\python\\system\\acsys.py), so this app reads the
fuel level from AC's shared memory instead, the same block
telemetry/shared_memory.py reads from outside the game.

Most AC apps do that with ctypes, which means bundling a
`_ctypes.pyd` binary because AC's Python ships without one. This app
skips ctypes: `mmap` and `struct` are built into AC's python33.dll,
and fuel is a single float at a fixed byte offset in the physics
block, so `struct.unpack_from` is enough.

Lap count and pit-lane state come from the regular `ac` API.

Python 3.3: no f-strings (see CLAUDE.md).
"""

import mmap
import os
import struct
import sys

import ac
import acsys

# AC imports this file with the AC install folder as the working
# directory, so make sibling modules importable explicitly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fuel_logic import FuelTracker, format_average, format_last_lap, format_litres  # noqa: E402

APP_NAME = "fuel_hud"
PLAYER_CAR = 0

# SPageFilePhysics layout: packetId (int32), gas (float), brake
# (float), fuel (float) -> fuel starts at byte 12, little-endian.
PHYSICS_TAG = "Local\\acpmf_physics"
PHYSICS_FUEL_OFFSET = 12
PHYSICS_READ_SIZE = 16

app_window = None
labels = {}
physics_map = None
tracker = FuelTracker()


def acMain(ac_version):
    global app_window, physics_map

    app_window = ac.newApp(APP_NAME)
    ac.setSize(app_window, 220, 150)
    ac.setTitle(app_window, "Fuel")

    rows = [
        ("fuel", "Tank"),
        ("current", "This lap"),
        ("last", "Last lap"),
        ("average", "Average"),
    ]
    for index, (key, caption) in enumerate(rows):
        y = 35 + index * 26
        caption_label = ac.addLabel(app_window, caption)
        ac.setPosition(caption_label, 10, y)
        value_label = ac.addLabel(app_window, "--")
        ac.setPosition(value_label, 90, y)
        labels[key] = value_label

    try:
        physics_map = mmap.mmap(-1, PHYSICS_READ_SIZE, tagname=PHYSICS_TAG, access=mmap.ACCESS_READ)
    except Exception as error:
        ac.log("{}: could not open shared memory: {}".format(APP_NAME, error))

    ac.log("{}: acMain finished".format(APP_NAME))
    return APP_NAME


def acUpdate(deltaT):
    fuel = read_fuel()
    if fuel is None:
        return

    tracker.update(
        fuel=fuel,
        completed_laps=ac.getCarState(PLAYER_CAR, acsys.CS.LapCount),
        in_pit_lane=bool(ac.isCarInPitline(PLAYER_CAR)),
    )

    ac.setText(labels["fuel"], format_litres(tracker.fuel))
    ac.setText(labels["current"], format_litres(tracker.current_lap_used))
    ac.setText(labels["last"], format_last_lap(tracker.last_lap))
    ac.setText(labels["average"], format_average(tracker.average_used, tracker.average_lap_count))


def acShutdown():
    if physics_map is not None:
        physics_map.close()
    ac.log("{}: acShutdown called".format(APP_NAME))


def read_fuel():
    if physics_map is None:
        return None
    return struct.unpack_from("<f", physics_map, PHYSICS_FUEL_OFFSET)[0]

