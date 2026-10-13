"""Helpers that drive a RaceState with synthetic frames, the way the
in-game app does once per frame."""

from pitwall_core.state import Frame, RaceState


def drive(state, samples):
    """Feed (fuel, completed_laps, in_pit_lane[, lap_progress[,
    lap_time_ms]]) tuples. Returns the fuel laps that closed."""
    closed = []
    for sample in samples:
        before = state.fuel.last_lap
        state.update(Frame(*sample))
        if state.fuel.last_lap is not before:
            closed.append(state.fuel.last_lap)
    return closed


def drive_lap(state, start_fuel, lap, used, lap_time_ms=120000, steps=100):
    """Drive one whole lap with progress and lap time, burning fuel
    evenly, ending just past the line. Returns the closed fuel lap."""
    samples = [
        (start_fuel - used * step / steps, lap, False, step / steps, lap_time_ms * step / steps)
        for step in range(1, steps)
    ]
    samples.append((start_fuel - used, lap + 1, False, 0.001, 5))
    return drive(state, samples)[-1]


def flying_laps(state, start_fuel, start_lap, usages):
    """Drive whole laps without progress data, one usage per lap,
    starting on the line. Returns the fuel left."""
    fuel = start_fuel
    lap = start_lap
    for used in usages:
        drive(state, [(fuel - used / 2, lap, False)])
        fuel -= used
        lap += 1
        drive(state, [(fuel, lap, False)])
    return fuel


def state_on_flying_lap():
    """Joined mid-lap, then crossed the line into lap 3 with 58.5 L,
    so the next lap is a clean one."""
    state = RaceState()
    drive(state, [(60.0, 2, False), (59.0, 2, False), (58.5, 3, False)])
    return state
