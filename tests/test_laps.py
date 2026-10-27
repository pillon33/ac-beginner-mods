import pytest

from pitwall_core.laps import (
    EXCLUDED_FIRST_LAP, EXCLUDED_PARTIAL, EXCLUDED_PIT, LapTracker, average,
)


def feed(laps, samples):
    """(completed_laps, in_pit_lane[, progress[, lap_time_ms]]) tuples;
    returns the laps that closed."""
    closed = []
    for sample in samples:
        update = laps.update(*sample)
        if update.closed_lap is not None:
            closed.append(update.closed_lap)
    return closed


class TestLapBoundaries:
    def test_joining_mid_lap_marks_that_lap_partial(self):
        closed = feed(LapTracker(), [(2, False), (3, False)])
        assert closed[0].excluded_reason == EXCLUDED_PARTIAL

    def test_first_lap_of_session_is_excluded(self):
        closed = feed(LapTracker(), [(0, False), (0, False), (1, False)])
        assert closed[0].excluded_reason == EXCLUDED_FIRST_LAP

    def test_clean_lap_is_valid_and_numbered_as_the_lap_completed(self):
        closed = feed(LapTracker(), [(2, False), (3, False), (4, False)])
        assert closed[1].is_valid
        assert closed[1].lap_number == 4

    def test_pit_lane_lap_is_excluded(self):
        closed = feed(LapTracker(), [(2, False), (3, False), (3, True), (4, False)])
        assert closed[1].excluded_reason == EXCLUDED_PIT

    def test_skipped_lap_counter_is_partial(self):
        closed = feed(LapTracker(), [(2, False), (3, False), (5, False)])
        assert closed[1].excluded_reason == EXCLUDED_PARTIAL


class TestSessionRestart:
    def test_counter_going_backwards_resets_and_reports_restart(self):
        laps = LapTracker()
        feed(laps, [(2, False, 0.5, 1000), (3, False, 0.0, 0)])
        update = laps.update(0, False, 0.98)
        assert update.restarted
        assert laps.last_lap is None
        assert laps.completed_laps == 0

    def test_first_lap_after_restart_is_excluded(self):
        laps = LapTracker()
        feed(laps, [(2, False), (3, False)])
        closed = feed(laps, [(0, False), (1, False)])
        assert closed[0].excluded_reason == EXCLUDED_FIRST_LAP


class TestLapProgress:
    def test_progress_held_at_zero_until_track_position_wraps_past_the_line(self):
        laps = LapTracker()
        laps.update(0, False, 0.98)
        assert laps.lap_progress == 0.0
        laps.update(0, False, 0.01)
        assert laps.lap_progress == 0.01
        laps.update(0, False, 0.6)
        assert laps.lap_progress == 0.6

    def test_progress_of_a_lap_joined_mid_way_is_taken_as_is(self):
        laps = LapTracker()
        laps.update(3, False, 0.7)
        assert laps.lap_progress == 0.7

    def test_progress_holds_after_each_line(self):
        laps = LapTracker()
        feed(laps, [(3, False, 0.7), (4, False, 0.99)])
        assert laps.lap_progress == 0.0


class TestLapTimes:
    def test_lap_time_comes_from_the_sample_before_the_line(self):
        closed = feed(LapTracker(), [(2, False), (3, False, 0.0, 0),
                                     (3, False, 0.99, 119000), (4, False, 0.0, 10)])
        assert closed[1].lap_time_ms == 119000

    def test_average_lap_time_uses_only_valid_laps(self):
        laps = LapTracker()
        feed(laps, [
            (2, False), (3, False, 0.0, 0),
            (3, False, 0.9, 100000), (4, False, 0.0, 0),   # valid
            (4, True, 0.9, 150000), (5, False, 0.0, 0),    # pit lap
            (5, False, 0.9, 110000), (6, False, 0.0, 0),   # valid
        ])
        assert laps.average_lap_time_ms == pytest.approx(105000)

    def test_no_average_lap_time_before_a_valid_lap(self):
        assert LapTracker().average_lap_time_ms is None


def test_average():
    assert average([]) is None
    assert average([1.0, 2.0, 3.0]) == pytest.approx(2.0)
