import pytest

from pitwall_core.race import (
    SESSION_PRACTICE, SESSION_RACE, SessionInfo, laps_to_flag, laps_to_go_lap_race,
    laps_to_go_timed,
)

SESSION_HOTLAP = 3


def test_laps_to_go_lap_race():
    assert laps_to_go_lap_race(25, 11, 0.42) == pytest.approx(13.58)
    assert laps_to_go_lap_race(25, 25, 0.1) == 0.0


@pytest.mark.parametrize("time_left_ms, progress, expected", [
    (300000, 0.0, 3.0),  # exactly 3 laps of time
    (250000, 0.0, 3.0),  # clock runs out during lap 3: finish it
    (250000, 0.5, 2.5),  # half a lap already done
    (30000, 0.5, 0.5),   # clock runs out this lap
    (0, 0.4, 0.6),       # clock already out: finish this lap
])
def test_laps_to_go_timed(time_left_ms, progress, expected):
    assert laps_to_go_timed(time_left_ms, 100000, progress) == pytest.approx(expected)


def test_laps_to_go_timed_extra_lap_and_missing_lap_time():
    assert laps_to_go_timed(250000, 100000, 0.0, has_extra_lap=True) == pytest.approx(4.0)
    assert laps_to_go_timed(250000, None, 0.0) is None


def test_laps_to_flag_lap_race():
    assert laps_to_flag(SessionInfo(SESSION_RACE, total_laps=25), 11, 0.42, None) == pytest.approx(13.58)


def test_laps_to_flag_timed_race_and_practice():
    race = SessionInfo(SESSION_RACE, time_left_ms=250000, is_timed_race=True, has_extra_lap=True)
    assert laps_to_flag(race, 3, 0.0, 100000) == pytest.approx(4.0)
    # The extra lap only applies to races.
    practice = SessionInfo(SESSION_PRACTICE, time_left_ms=250000, has_extra_lap=True)
    assert laps_to_flag(practice, 3, 0.0, 100000) == pytest.approx(3.0)


def test_laps_to_flag_unknown():
    assert laps_to_flag(SessionInfo(SESSION_HOTLAP, time_left_ms=9e9), 3, 0.5, 100000) is None
    assert laps_to_flag(SessionInfo(SESSION_PRACTICE, time_left_ms=0), 3, 0.5, 100000) is None
    assert laps_to_flag(SessionInfo(SESSION_RACE, total_laps=25), 3, None, None) is None
    assert laps_to_flag(None, 3, 0.5, 100000) is None
