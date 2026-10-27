import os

import pytest

from conftest import REPO_ROOT
from driving import drive, flying_laps, state_on_flying_lap
from pitwall_core.display import STATUS_BAD, STATUS_RGBA
from pitwall_core.race import SESSION_RACE, SessionInfo
from pitwall_core.state import Frame, RaceState
from pitwall_core.windows import WINDOWS, car_readout, fuel_readout


@pytest.mark.parametrize("spec", WINDOWS, ids=lambda spec: spec.name)
def test_readout_fills_exactly_the_window_rows(spec):
    state = RaceState()
    state.update(Frame(fuel=40.0, completed_laps=2, in_pit_lane=False, lap_progress=0.3,
                       speed_kmh=120.0, gear=4, session=SessionInfo(SESSION_RACE, total_laps=10)))
    readout = spec.readout(state)
    assert set(readout) == set(key for key, _ in spec.rows)
    for text, status in readout.values():
        assert isinstance(text, str)
        assert status in STATUS_RGBA


def test_window_names_are_prefixed_and_unique():
    names = [spec.name for spec in WINDOWS]
    assert len(names) == len(set(names))
    # AC window names are global across every installed app.
    assert all(name.startswith("pitwall_") for name in names)


@pytest.mark.parametrize("spec", WINDOWS, ids=lambda spec: spec.name)
@pytest.mark.parametrize("state", ["ON", "OFF"])
def test_every_window_ships_app_bar_icons(spec, state):
    # AC shows a blank app-bar entry without both of these.
    icon = os.path.join(REPO_ROOT, "content", "gui", "icons", "{}_{}.png".format(spec.name, state))
    assert os.path.isfile(icon), "missing icon {}".format(icon)


def test_fuel_readout_before_any_lap_shows_tank_only():
    state = RaceState()
    drive(state, [(60.0, 2, False)])
    readout = fuel_readout(state)
    assert readout["fuel"] == ("60.00 L", None)
    assert readout["laps_left"] == ("--", None)
    assert readout["to_flag"] == ("--", None)


def test_fuel_readout_flags_a_deficit_in_a_lap_race():
    state = state_on_flying_lap()
    session = SessionInfo(SESSION_RACE, total_laps=20)
    for sample in [(58.5 - 4.0, 4, False), (58.5 - 8.0, 5, False)]:
        state.update(Frame(*sample, lap_progress=0.0, session=session))
    # 50.5 L, 15 laps to go at 4 L/lap needs 60 L.
    readout = fuel_readout(state)
    assert readout["laps_left"] == ("12.6", None)
    assert readout["to_flag"] == ("-9.50 L (-2.4 laps)", STATUS_BAD)
    assert readout["target"] == ("3.37 L/lap", None)


def test_car_readout():
    state = RaceState()
    state.update(Frame(fuel=40.0, completed_laps=0, in_pit_lane=False, speed_kmh=187.4, gear=5))
    assert car_readout(state) == {"speed": ("187 km/h", None), "gear": ("4", None)}


def test_flying_laps_helper_keeps_state_consistent():
    state = state_on_flying_lap()
    flying_laps(state, 58.5, 3, [4.0, 4.0])
    assert state.laps.completed_laps == 5
