"""
fuel_hud.py — in-game Assetto Corsa app for fuel: what's in the tank,
how many laps it lasts, whether it reaches the flag, and how this lap
is going against the consumption you can afford.

This file is the thin edge between the game and fuel_logic.py: it
reads the game every frame, hands the numbers to a FuelTracker and the
race-maths functions, and writes the results into labels. All the
logic lives in fuel_logic.py, where pytest can reach it.

WHERE THE NUMBERS COME FROM
----------------------------
`ac.getCarState()` has no fuel entry (see the CS list in
<AC install>\\apps\\python\\system\\acsys.py), and nothing in the `ac`
API says how long the session is. Both come from AC's shared memory
instead, read through ac_memory.py (mmap + struct, no ctypes; see the
note there).

From the regular `ac` API: completed laps, lap progress (track
position 0..1), current lap time and pit-lane state.

Python 3.3: no f-strings (see CLAUDE.md).
"""

import os
import sys

import ac
import acsys

# AC imports this file with the AC install folder as the working
# directory, so make sibling modules importable explicitly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ac_memory  # noqa: E402
from fuel_logic import (  # noqa: E402
    STATUS_BAD, STATUS_GOOD, STATUS_WARN,
    FuelTracker, SessionInfo,
    format_average, format_current_lap, format_last_lap, format_laps,
    format_litres, format_surplus, format_target,
    lap_budget_delta, lap_budget_status, laps_of_fuel, laps_to_flag,
    surplus_status, surplus_to_flag, target_per_lap,
)

APP_NAME = "fuel_hud"
PLAYER_CAR = 0

ROWS = [
    ("fuel", "Tank"),
    ("laps_left", "Laps left"),
    ("to_flag", "To flag"),
    ("target", "Target"),
    ("current", "This lap"),
    ("last", "Last lap"),
    ("average", "Average"),
]

# RGBA for ac.setFontColor.
STATUS_COLOURS = {
    STATUS_GOOD: (0.4, 0.9, 0.55, 1.0),
    STATUS_WARN: (1.0, 0.78, 0.3, 1.0),
    STATUS_BAD: (1.0, 0.42, 0.36, 1.0),
    None: (1.0, 1.0, 1.0, 1.0),
}

app_window = None
labels = {}
physics = None
graphics = None
static = None
tracker = FuelTracker()
logged_session = False


def acMain(ac_version):
    global app_window, physics, graphics, static

    app_window = ac.newApp(APP_NAME)
    ac.setSize(app_window, 270, 40 + len(ROWS) * 24)
    ac.setTitle(app_window, "Fuel")

    for index, (key, caption) in enumerate(ROWS):
        y = 35 + index * 24
        caption_label = ac.addLabel(app_window, caption)
        ac.setPosition(caption_label, 10, y)
        value_label = ac.addLabel(app_window, "--")
        ac.setPosition(value_label, 90, y)
        labels[key] = value_label

    try:
        physics = ac_memory.SharedMemoryBlock(ac_memory.PHYSICS_TAG, ac_memory.PHYSICS_READ_SIZE)
        graphics = ac_memory.SharedMemoryBlock(ac_memory.GRAPHICS_TAG, ac_memory.GRAPHICS_READ_SIZE)
        static = ac_memory.SharedMemoryBlock(ac_memory.STATIC_TAG, ac_memory.STATIC_READ_SIZE)
    except Exception as error:
        physics = None
        ac.log("{}: could not open shared memory: {}".format(APP_NAME, error))

    ac.log("{}: acMain finished".format(APP_NAME))
    return APP_NAME


def acUpdate(deltaT):
    if physics is None:
        return

    session = read_session()
    log_session_once(session)

    completed_laps = ac.getCarState(PLAYER_CAR, acsys.CS.LapCount)
    tracker.update(
        fuel=physics.float_at(ac_memory.PHYSICS_FUEL),
        completed_laps=completed_laps,
        in_pit_lane=bool(ac.isCarInPitline(PLAYER_CAR)),
        lap_progress=ac.getCarState(PLAYER_CAR, acsys.CS.NormalizedSplinePosition),
        lap_time_ms=ac.getCarState(PLAYER_CAR, acsys.CS.LapTime),
    )

    per_lap = tracker.average_used
    laps_to_go = laps_to_flag(session, completed_laps, tracker.lap_progress,
                              tracker.average_lap_time_ms)
    surplus = surplus_to_flag(tracker.fuel, laps_to_go, per_lap)
    target = target_per_lap(tracker.lap_start_fuel, laps_to_go, tracker.lap_progress)
    delta = lap_budget_delta(tracker.current_lap_used, target, tracker.lap_progress,
                             tracker.reference_profile)

    show("fuel", format_litres(tracker.fuel))
    show("laps_left", format_laps(laps_of_fuel(tracker.fuel, per_lap)))
    show("to_flag", format_surplus(surplus, per_lap), surplus_status(surplus, per_lap))
    show("target", format_target(target))
    show("current", format_current_lap(tracker.current_lap_used, delta),
         lap_budget_status(delta, target))
    show("last", format_last_lap(tracker.last_lap))
    show("average", format_average(per_lap, tracker.average_lap_count))


def acShutdown():
    for block in (physics, graphics, static):
        if block is not None:
            block.close()
    ac.log("{}: acShutdown called".format(APP_NAME))


def read_session():
    return SessionInfo(
        session_type=graphics.int_at(ac_memory.GRAPHICS_SESSION),
        total_laps=graphics.int_at(ac_memory.GRAPHICS_NUMBER_OF_LAPS),
        time_left_ms=graphics.float_at(ac_memory.GRAPHICS_SESSION_TIME_LEFT),
        is_timed_race=bool(static.int_at(ac_memory.STATIC_IS_TIMED_RACE)),
        has_extra_lap=bool(static.int_at(ac_memory.STATIC_HAS_EXTRA_LAP)),
    )


def log_session_once(session):
    # The shared memory offsets are taken from Kunos' struct layout but
    # haven't been checked live yet: log what they read once, so a
    # wrong offset shows up in py_log.txt as an implausible value.
    global logged_session
    if logged_session:
        return
    logged_session = True
    ac.log("{}: session={} laps={} time_left_ms={:.0f} timed_race={} extra_lap={} fuel={:.2f}".format(
        APP_NAME, session.session_type, session.total_laps, session.time_left_ms,
        session.is_timed_race, session.has_extra_lap, physics.float_at(ac_memory.PHYSICS_FUEL)))


def show(key, text, status=None):
    ac.setText(labels[key], text)
    r, g, b, a = STATUS_COLOURS[status]
    ac.setFontColor(labels[key], r, g, b, a)
