"""Hotlap-style starts: the car is placed before the line with the lap
clock already running. AC's clock may keep counting through the first
crossing and its lap counter may not move until a later one; the first
crossing must still start a fresh lap."""

import pytest

from pitwall_core.laps import EXCLUDED_FIRST_LAP
from pitwall_core.sectors import MINI_SECTORS
from pitwall_core.state import Frame, RaceState

LAP_MS = 90000
LAP_FUEL = 4.0
START_POSITION = 0.97
START_CLOCK = 10000
FRAMES_PER_LAP = 400


def hotlap_frames(variant, laps=3):
    """Yield (completed_laps, position, clock_ms, fuel) per frame.

    variant "counter": the lap counter goes up at the first crossing,
    the clock keeps counting until the second.
    variant "no-counter": neither moves at the first crossing.
    variant "reset": the clock restarts at every crossing, as on a
    standing start (the plain case must keep working).
    """
    pre_ms = (1.0 - START_POSITION) * LAP_MS
    fuel = 60.0
    step = 1.0 / FRAMES_PER_LAP
    # Out lap: START_POSITION to the line.
    position = START_POSITION
    while position < 1.0:
        yield 0, position, START_CLOCK + (position - START_POSITION) * LAP_MS, fuel
        position += step
        fuel -= LAP_FUEL * step
    base = START_CLOCK + pre_ms                      # clock at the first crossing
    for lap in range(1, laps + 1):
        for k in range(FRAMES_PER_LAP):
            position = k * step
            if variant == "reset" or lap > 1:
                clock = position * LAP_MS
            else:
                clock = base + position * LAP_MS     # clock kept counting
            yield counter_for(variant, lap), position, clock, fuel
            fuel -= LAP_FUEL * step
    # Cross the line once more so the last lap closes.
    yield counter_for(variant, laps + 1), 0.0, 0.0, fuel


def counter_for(variant, lap):
    """The counter reading on lap `lap` (1 = the first lap after the
    out lap); in the "no-counter" variant it lags one behind."""
    return lap - 1 if variant == "no-counter" else lap


def drive(variant, laps=3):
    state = RaceState()
    closed = []
    fuel_closed = []
    for counter, position, clock, fuel in hotlap_frames(variant, laps):
        before = state.fuel.last_lap
        state.update(Frame(fuel=fuel, completed_laps=counter, in_pit_lane=False,
                           lap_progress=position, lap_time_ms=clock))
        if state.laps.last_lap not in closed and state.laps.last_lap is not None:
            closed.append(state.laps.last_lap)
        if state.fuel.last_lap is not before:
            fuel_closed.append(state.fuel.last_lap)
    return state, closed, fuel_closed


@pytest.mark.parametrize("variant", ["counter", "no-counter", "reset"])
def test_first_crossing_closes_the_out_lap_and_starts_a_fresh_lap(variant):
    _, closed, _ = drive(variant)
    assert closed[0].excluded_reason == EXCLUDED_FIRST_LAP
    # The first full lap is valid and measured from the line, not from
    # the start of the session.
    assert closed[1].is_valid
    assert closed[1].lap_time_ms == pytest.approx(LAP_MS, abs=250)
    assert closed[2].lap_time_ms == pytest.approx(LAP_MS, abs=250)


@pytest.mark.parametrize("variant", ["counter", "no-counter", "reset"])
def test_current_lap_time_counts_from_the_crossing(variant):
    state = RaceState()
    for counter, position, clock, fuel in hotlap_frames(variant):
        state.update(Frame(fuel=fuel, completed_laps=counter, in_pit_lane=False,
                           lap_progress=position, lap_time_ms=clock))
        if counter == counter_for(variant, 1) and abs(position - 0.5) < 0.001 \
                and clock > START_CLOCK:
            assert state.laps.lap_time_ms == pytest.approx(0.5 * LAP_MS, abs=250)
            break
    else:
        pytest.fail("never reached mid lap one")


def test_timer_before_the_first_crossing_shows_the_running_clock():
    state = RaceState()
    state.update(Frame(fuel=60.0, completed_laps=0, in_pit_lane=False,
                       lap_progress=START_POSITION, lap_time_ms=START_CLOCK))
    assert state.laps.lap_time_ms == START_CLOCK


@pytest.mark.parametrize("variant", ["counter", "no-counter", "reset"])
def test_fuel_per_lap_excludes_the_out_lap(variant):
    state, _, fuel_closed = drive(variant)
    assert fuel_closed[0].excluded_reason == EXCLUDED_FIRST_LAP
    assert fuel_closed[1].is_valid
    assert fuel_closed[1].fuel_used == pytest.approx(LAP_FUEL, abs=0.05)
    assert state.fuel.average_used == pytest.approx(LAP_FUEL, abs=0.05)


@pytest.mark.parametrize("variant", ["counter", "no-counter", "reset"])
def test_mini_sectors_ignore_the_out_lap_and_use_lap_one(variant):
    state, _, _ = drive(variant, laps=2)
    # The out lap contributed nothing; lap 1 (from the line) set every slice.
    assert sorted(state.sectors.best_ms) == list(range(MINI_SECTORS))
    assert state.sectors.theoretical_best_ms == pytest.approx(LAP_MS, abs=250)


def test_delta_on_the_second_lap_is_against_the_first_lap_not_the_session_clock():
    state = RaceState()
    deltas = []
    for counter, position, clock, fuel in hotlap_frames("counter", laps=3):
        state.update(Frame(fuel=fuel, completed_laps=counter, in_pit_lane=False,
                           lap_progress=position, lap_time_ms=clock))
        if counter == 2 and 0.2 < position < 0.8:
            deltas.append(state.sectors.delta_ms)
    assert deltas and all(d is not None and abs(d) < 250 for d in deltas)


def test_standing_start_with_clock_reset_at_the_line_still_works():
    state = RaceState()
    closed = []
    # Grid sits just behind the line, clock idle, then restarts at the line.
    frames = [(0, 0.995, 0)] * 3 + [(0, 0.996 + 0.001 * i, 1000 + 100 * i) for i in range(3)]
    frames += [(1, 0.001 * (i + 1), 100 * i) for i in range(3)]
    for counter, position, clock in frames:
        state.update(Frame(fuel=60.0, completed_laps=counter, in_pit_lane=False,
                           lap_progress=position, lap_time_ms=clock))
    assert state.laps.last_lap.excluded_reason == EXCLUDED_FIRST_LAP
    assert state.laps.lap_time_ms == pytest.approx(200)


def test_pit_exit_lap_stays_excluded():
    state = RaceState()
    # Run a clean lap, then a lap with a pit visit.
    samples = []
    for lap in range(1, 4):
        for k in range(100):
            samples.append((lap, k / 100.0, k * 900, lap == 2 and 10 < k < 20))
    for counter, position, clock, pit in samples:
        state.update(Frame(fuel=50.0, completed_laps=counter, in_pit_lane=pit,
                           lap_progress=position, lap_time_ms=clock))
    state.update(Frame(fuel=50.0, completed_laps=4, in_pit_lane=False, lap_progress=0.0,
                       lap_time_ms=0))
    assert state.laps.last_lap.is_valid           # lap 3 was clean
    assert state.laps.last_lap.lap_number == 4


@pytest.mark.parametrize("variant", ["counter", "no-counter", "reset"])
def test_one_lap_after_the_out_lap_is_enough_for_a_reference(variant):
    state, _, _ = drive(variant, laps=1)
    assert sorted(state.sectors.best_ms) == list(range(MINI_SECTORS))
    assert state.sectors.theoretical_best_ms == pytest.approx(LAP_MS, abs=250)
