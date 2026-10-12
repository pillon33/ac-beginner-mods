import pytest

from fuel_logic import (
    EXCLUDED_FIRST_LAP,
    EXCLUDED_PARTIAL,
    EXCLUDED_PIT,
    EXCLUDED_REFUEL,
    FuelTracker,
    LapRecord,
    average,
    format_average,
    format_last_lap,
    format_litres,
)


def drive(tracker, samples):
    """Feed (fuel, completed_laps, in_pit_lane) tuples; return the
    laps that closed along the way."""
    closed = []
    for fuel, laps, in_pit in samples:
        lap = tracker.update(fuel=fuel, completed_laps=laps, in_pit_lane=in_pit)
        if lap is not None:
            closed.append(lap)
    return closed


def flying_laps(tracker, start_fuel, start_lap, usages):
    """Drive whole laps on track, one usage per lap, starting exactly
    on the line. Returns the fuel left."""
    fuel = start_fuel
    lap = start_lap
    for used in usages:
        drive(tracker, [(fuel - used / 2, lap, False)])
        fuel -= used
        lap += 1
        drive(tracker, [(fuel, lap, False)])
    return fuel


@pytest.fixture
def tracker_on_flying_lap():
    """A tracker that joined mid-lap and has just crossed the line
    into lap 3, so the next lap is a clean one."""
    tracker = FuelTracker()
    drive(tracker, [(60.0, 2, False), (59.0, 2, False), (58.5, 3, False)])
    return tracker


class TestBeforeAnyLap:
    def test_everything_is_empty_before_the_first_sample(self):
        tracker = FuelTracker()
        assert tracker.fuel is None
        assert tracker.current_lap_used is None
        assert tracker.last_lap_used is None
        assert tracker.average_used is None

    def test_current_lap_counts_from_the_first_sample(self):
        tracker = FuelTracker()
        drive(tracker, [(50.0, 4, False), (49.25, 4, False)])
        assert tracker.fuel == 49.25
        assert tracker.current_lap_used == pytest.approx(0.75)


class TestLapAccounting:
    def test_joining_mid_lap_marks_that_lap_partial(self):
        tracker = FuelTracker()
        closed = drive(tracker, [(60.0, 2, False), (58.5, 3, False)])
        assert closed[0].excluded_reason == EXCLUDED_PARTIAL
        assert closed[0].fuel_used == pytest.approx(1.5)
        assert tracker.average_used is None

    def test_clean_lap_counts_towards_average(self, tracker_on_flying_lap):
        flying_laps(tracker_on_flying_lap, 58.5, 3, [4.1])
        assert tracker_on_flying_lap.last_lap_used == pytest.approx(4.1)
        assert tracker_on_flying_lap.last_lap.is_valid
        assert tracker_on_flying_lap.average_used == pytest.approx(4.1)

    def test_current_lap_resets_on_the_line(self, tracker_on_flying_lap):
        assert tracker_on_flying_lap.current_lap_used == 0.0

    def test_lap_number_is_the_lap_just_completed(self, tracker_on_flying_lap):
        closed = drive(tracker_on_flying_lap, [(54.4, 4, False)])
        assert closed[0].lap_number == 4

    def test_first_lap_of_session_is_excluded(self):
        tracker = FuelTracker()
        closed = drive(tracker, [(60.0, 0, False), (57.0, 0, False), (55.7, 1, False)])
        assert closed[0].excluded_reason == EXCLUDED_FIRST_LAP
        assert closed[0].fuel_used == pytest.approx(4.3)

    def test_pit_lane_lap_is_excluded(self, tracker_on_flying_lap):
        closed = drive(tracker_on_flying_lap, [
            (56.0, 3, False),
            (55.0, 3, True),
            (54.5, 4, False),
        ])
        assert closed[0].excluded_reason == EXCLUDED_PIT
        assert tracker_on_flying_lap.average_used is None

    def test_refuel_is_excluded_and_current_lap_restarts_from_new_level(
            self, tracker_on_flying_lap):
        drive(tracker_on_flying_lap, [(57.0, 3, True), (80.0, 3, True)])
        assert tracker_on_flying_lap.current_lap_used == 0.0

        closed = drive(tracker_on_flying_lap, [(77.0, 4, False)])
        assert closed[0].excluded_reason == EXCLUDED_REFUEL
        assert closed[0].fuel_used == pytest.approx(3.0)

    def test_small_upward_noise_is_not_a_refuel(self, tracker_on_flying_lap):
        closed = drive(tracker_on_flying_lap, [
            (56.0, 3, False),
            (56.05, 3, False),
            (54.4, 4, False),
        ])
        assert closed[0].is_valid

    def test_skipped_lap_counter_is_excluded(self, tracker_on_flying_lap):
        closed = drive(tracker_on_flying_lap, [(50.0, 5, False)])
        assert closed[0].excluded_reason == EXCLUDED_PARTIAL

    def test_fuel_used_never_negative(self, tracker_on_flying_lap):
        closed = drive(tracker_on_flying_lap, [(58.55, 4, False)])
        assert closed[0].fuel_used >= 0.0


class TestAverage:
    def test_average_uses_only_the_last_five_valid_laps(self, tracker_on_flying_lap):
        flying_laps(tracker_on_flying_lap, 58.5, 3, [9.0, 4.0, 4.0, 4.2, 4.2, 4.1])
        assert tracker_on_flying_lap.average_lap_count == 5
        assert tracker_on_flying_lap.average_used == pytest.approx(4.1)

    def test_excluded_laps_do_not_dilute_the_average(self, tracker_on_flying_lap):
        fuel = flying_laps(tracker_on_flying_lap, 58.5, 3, [4.0])
        drive(tracker_on_flying_lap, [(fuel - 1, 4, True), (fuel - 6, 5, False)])
        flying_laps(tracker_on_flying_lap, fuel - 6, 5, [4.2])
        assert tracker_on_flying_lap.average_lap_count == 2
        assert tracker_on_flying_lap.average_used == pytest.approx(4.1)

    def test_window_is_configurable(self):
        tracker = FuelTracker(average_window=2)
        drive(tracker, [(60.0, 2, False), (59.0, 3, False)])
        flying_laps(tracker, 59.0, 3, [5.0, 4.0, 3.0])
        assert tracker.average_used == pytest.approx(3.5)

    def test_average_helper(self):
        assert average([]) is None
        assert average([1.0, 2.0, 3.0]) == pytest.approx(2.0)


class TestSessionRestart:
    def test_lap_counter_going_backwards_resets_everything(self, tracker_on_flying_lap):
        flying_laps(tracker_on_flying_lap, 58.5, 3, [4.0, 4.0])
        assert tracker_on_flying_lap.average_used is not None

        drive(tracker_on_flying_lap, [(60.0, 0, False)])
        assert tracker_on_flying_lap.average_used is None
        assert tracker_on_flying_lap.last_lap is None
        assert tracker_on_flying_lap.fuel == 60.0
        assert tracker_on_flying_lap.current_lap_used == 0.0

    def test_first_lap_after_restart_is_excluded(self, tracker_on_flying_lap):
        drive(tracker_on_flying_lap, [(60.0, 0, False)])
        closed = drive(tracker_on_flying_lap, [(55.8, 1, False)])
        assert closed[0].excluded_reason == EXCLUDED_FIRST_LAP
        assert tracker_on_flying_lap.average_used is None


class TestFormatting:
    def test_format_litres(self):
        assert format_litres(None) == "--"
        assert format_litres(51.8) == "51.80 L"

    def test_format_last_lap(self):
        assert format_last_lap(None) == "--"
        assert format_last_lap(LapRecord(4, 4.08)) == "4.08 L"
        assert format_last_lap(LapRecord(4, 4.31, EXCLUDED_PIT)) == "4.31 L (pit)"

    def test_format_average(self):
        assert format_average(None, 0) == "--"
        assert format_average(4.106, 5) == "4.11 L (5 laps)"
