"""
windows.py — what each in-game window shows.

A window is a name, a title, its rows (key, caption) and a readout
function that turns the RaceState into {key: (text, status)}. The app
draws them; nothing here touches `ac`, so every readout is testable.

To add a window: write a readout, add a WindowSpec to WINDOWS.
"""

from pitwall_core.display import (
    format_average, format_current_lap, format_fuel_lap, format_gear, format_laps,
    format_litres, format_speed, format_surplus, format_target,
)
from pitwall_core.fuel import (
    lap_budget_delta, lap_budget_status, laps_of_fuel, surplus_status, surplus_to_flag,
    target_per_lap,
)


class WindowSpec(object):

    def __init__(self, name, title, rows, readout, width=270):
        # `name` is AC's id for the window: it's what the app bar
        # shows and what AC looks for an icon by. Prefixed, because
        # it has to be unique across every installed app.
        self.name = name
        self.title = title
        self.rows = rows
        self.readout = readout
        self.width = width


FUEL_ROWS = [
    ("fuel", "Tank"),
    ("laps_left", "Laps left"),
    ("to_flag", "To flag"),
    ("target", "Target"),
    ("current", "This lap"),
    ("last", "Last lap"),
    ("average", "Average"),
]


def fuel_readout(state):
    fuel = state.fuel
    progress = state.laps.lap_progress
    per_lap = fuel.average_used
    laps_to_go = state.laps_to_flag
    surplus = surplus_to_flag(fuel.fuel, laps_to_go, per_lap)
    target = target_per_lap(fuel.lap_start_fuel, laps_to_go, progress)
    delta = lap_budget_delta(fuel.current_lap_used, target, progress, fuel.reference_profile)
    return {
        "fuel": (format_litres(fuel.fuel), None),
        "laps_left": (format_laps(laps_of_fuel(fuel.fuel, per_lap)), None),
        "to_flag": (format_surplus(surplus, per_lap), surplus_status(surplus, per_lap)),
        "target": (format_target(target), None),
        "current": (format_current_lap(fuel.current_lap_used, delta),
                    lap_budget_status(delta, target)),
        "last": (format_fuel_lap(fuel.last_lap), None),
        "average": (format_average(per_lap, fuel.average_lap_count), None),
    }


CAR_ROWS = [
    ("speed", "Speed"),
    ("gear", "Gear"),
]


def car_readout(state):
    frame = state.frame
    return {
        "speed": (format_speed(frame.speed_kmh), None),
        "gear": (format_gear(frame.gear), None),
    }


WINDOWS = (
    WindowSpec("pitwall_fuel", "Fuel", FUEL_ROWS, fuel_readout),
    WindowSpec("pitwall_car", "Car", CAR_ROWS, car_readout, width=200),
)
