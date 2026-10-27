"""
windows.py — what each in-game window shows.

A window is a name, a title, its rows (key, caption) and a readout
function that turns the RaceState into {key: (text, status)}. The app
draws them; nothing here touches `ac`, so every readout is testable.

To add a window: write a readout, add a WindowSpec to WINDOWS.
"""

from pitwall_core.display import (
    delta_status, format_average, format_current_lap, format_delta, format_fuel_lap, format_gear,
    format_lap_time, format_laps, format_litres, format_speed, format_surplus, format_target,
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


TIME_ROWS = [
    ("lap", "Lap"),
    ("theoretical", "Theoretical"),
    ("delta", "Delta"),
]


def time_readout(state):
    """Lap timer and pace against the theoretical best lap.

    theoretical: sum of the best sector times this session (needs a
    counted time in every sector, see sectors.py), '--' until then.

    delta: the current lap's sector times so far minus the best times
    of those same sectors, i.e. how far off the theoretical pace the
    lap has been at its last sector split. Updates at each split, holds
    across the line (after a lap it is that lap's full gap) and is
    '--' until a theoretical best exists or when the lap has an
    uncounted sector (pit, joined mid-lap). It is never negative:
    the best sectors include the lap's own.
    """
    sectors = state.sectors
    theoretical = sectors.theoretical_best_ms
    delta = sectors.delta_ms if theoretical is not None else None
    return {
        "lap": (format_lap_time(state.frame.lap_time_ms), None),
        "theoretical": (format_lap_time(theoretical), None),
        "delta": (format_delta(delta), delta_status(delta)),
    }


WINDOWS = (
    WindowSpec("pitwall_fuel", "Fuel", FUEL_ROWS, fuel_readout),
    WindowSpec("pitwall_time", "Time", TIME_ROWS, time_readout, width=230),
    WindowSpec("pitwall_car", "Car", CAR_ROWS, car_readout, width=200),
)
