import pytest

from fuel_logic import (
    EXCLUDED_FIRST_LAP,
    EXCLUDED_PARTIAL,
    EXCLUDED_PIT,
    EXCLUDED_REFUEL,
    PROFILE_BUCKETS,
    SESSION_PRACTICE,
    SESSION_RACE,
    STATUS_BAD,
    STATUS_GOOD,
    STATUS_WARN,
    FuelTracker,
    LapRecord,
    SessionInfo,
    average,
    build_profile,
    format_average,
    format_current_lap,
    format_last_lap,
    format_laps,
    format_litres,
    format_surplus,
    format_target,
    lap_budget_delta,
    lap_budget_status,
    laps_of_fuel,
    laps_to_flag,
    laps_to_go_lap_race,
    laps_to_go_timed,
    profile_share,
    surplus_status,
    surplus_to_flag,
    target_per_lap,
)

SESSION_HOTLAP = 3


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

    def test_format_laps(self):
        assert format_laps(None) == "--"
        assert format_laps(12.603) == "12.6"

    def test_format_surplus_uses_ascii_signs(self):
        assert format_surplus(2.3, 4.0) == "+2.30 L (+0.6 laps)"
        assert format_surplus(-4.0, 4.0) == "-4.00 L (-1.0 laps)"
        assert format_surplus(None, 4.0) == "--"

    def test_format_target(self):
        assert format_target(None) == "--"
        assert format_target(3.814) == "3.81 L/lap"

    def test_format_current_lap(self):
        assert format_current_lap(1.73, 0.04) == "1.73 L (+0.04)"
        assert format_current_lap(1.73, -0.04) == "1.73 L (-0.04)"
        assert format_current_lap(1.73, None) == "1.73 L"
        assert format_current_lap(None, 0.04) == "--"


def drive_lap_with_profile(tracker, start_fuel, lap, used, lap_time_ms=120000, steps=100):
    """Drive one whole lap with progress and lap time, burning fuel
    evenly. Ends just past the line of the next lap."""
    for step in range(1, steps):
        progress = step / steps
        tracker.update(fuel=start_fuel - used * progress, completed_laps=lap, in_pit_lane=False,
                       lap_progress=progress, lap_time_ms=lap_time_ms * progress)
    return tracker.update(fuel=start_fuel - used, completed_laps=lap + 1, in_pit_lane=False,
                          lap_progress=0.001, lap_time_ms=5)


class TestLapProgressAndTime:
    def test_progress_held_at_zero_until_track_position_wraps_past_the_line(self):
        tracker = FuelTracker()
        tracker.update(fuel=60.0, completed_laps=0, in_pit_lane=False, lap_progress=0.98)
        assert tracker.lap_progress == 0.0
        tracker.update(fuel=60.0, completed_laps=0, in_pit_lane=False, lap_progress=0.01)
        assert tracker.lap_progress == 0.01
        tracker.update(fuel=59.0, completed_laps=0, in_pit_lane=False, lap_progress=0.6)
        assert tracker.lap_progress == 0.6

    def test_progress_of_a_lap_joined_mid_way_is_taken_as_is(self):
        tracker = FuelTracker()
        tracker.update(fuel=60.0, completed_laps=3, in_pit_lane=False, lap_progress=0.7)
        assert tracker.lap_progress == 0.7

    def test_lap_time_comes_from_the_sample_before_the_line(self, tracker_on_flying_lap):
        lap = drive_lap_with_profile(tracker_on_flying_lap, 58.5, 3, 4.0, lap_time_ms=120000)
        assert lap.lap_time_ms == pytest.approx(120000 * 0.99)

    def test_average_lap_time_uses_valid_laps(self, tracker_on_flying_lap):
        drive_lap_with_profile(tracker_on_flying_lap, 58.5, 3, 4.0, lap_time_ms=100000)
        drive_lap_with_profile(tracker_on_flying_lap, 54.5, 4, 4.0, lap_time_ms=110000)
        assert tracker_on_flying_lap.average_lap_time_ms == pytest.approx(105000 * 0.99)


class TestReferenceProfile:
    def test_valid_lap_becomes_the_reference_profile(self, tracker_on_flying_lap):
        assert tracker_on_flying_lap.reference_profile is None
        drive_lap_with_profile(tracker_on_flying_lap, 58.5, 3, 4.0)
        profile = tracker_on_flying_lap.reference_profile
        assert len(profile) == PROFILE_BUCKETS + 1
        assert profile[0] == 0.0 and profile[-1] == 1.0
        assert profile_share(profile, 0.5) == pytest.approx(0.5, abs=0.03)

    def test_excluded_lap_does_not_replace_the_profile(self, tracker_on_flying_lap):
        drive_lap_with_profile(tracker_on_flying_lap, 58.5, 3, 4.0)
        before = tracker_on_flying_lap.reference_profile
        tracker_on_flying_lap.update(fuel=54.0, completed_laps=4, in_pit_lane=True, lap_progress=0.5)
        tracker_on_flying_lap.update(fuel=53.0, completed_laps=5, in_pit_lane=False, lap_progress=0.0)
        assert tracker_on_flying_lap.reference_profile is before

    def test_build_profile_follows_uneven_burn(self):
        # The first half of the lap burns 3 of the 4 litres.
        samples = ([3.0 * (i + 1) / 25 for i in range(25)]
                   + [3.0 + (i + 1) / 25 for i in range(25)])
        profile = build_profile(samples, 4.0)
        assert profile_share(profile, 0.5) == pytest.approx(0.75)

    def test_build_profile_fills_gaps_and_never_decreases(self):
        profile = build_profile([None, 1.0, None, 0.5, 2.0], 2.0)
        assert profile == [0.0, 0.0, 0.5, 0.5, 0.5, 1.0]

    def test_build_profile_rejects_sparse_or_empty_laps(self):
        assert build_profile([None] * 10 + [1.0], 1.0) is None
        assert build_profile([1.0] * 10, 0.0) is None

    def test_profile_share_without_profile_is_linear(self):
        assert profile_share(None, 0.3) == 0.3
        assert profile_share(None, 1.5) == 1.0


class TestRaceMaths:
    def test_laps_of_fuel(self):
        assert laps_of_fuel(51.8, 4.11) == pytest.approx(12.6, abs=0.01)
        assert laps_of_fuel(51.8, None) is None
        assert laps_of_fuel(51.8, 0.0) is None

    def test_laps_to_go_lap_race(self):
        assert laps_to_go_lap_race(25, 11, 0.42) == pytest.approx(13.58)
        assert laps_to_go_lap_race(25, 25, 0.1) == 0.0

    @pytest.mark.parametrize("time_left_ms, progress, expected", [
        (300000, 0.0, 3.0),  # exactly 3 laps of time
        (250000, 0.0, 3.0),  # clock runs out during lap 3: finish it
        (250000, 0.5, 2.5),  # half a lap already done
        (30000, 0.5, 0.5),   # clock runs out this lap
        (0, 0.4, 0.6),       # clock already out: finish this lap
    ])
    def test_laps_to_go_timed(self, time_left_ms, progress, expected):
        assert laps_to_go_timed(time_left_ms, 100000, progress) == pytest.approx(expected)

    def test_laps_to_go_timed_extra_lap_and_missing_lap_time(self):
        assert laps_to_go_timed(250000, 100000, 0.0, has_extra_lap=True) == pytest.approx(4.0)
        assert laps_to_go_timed(250000, None, 0.0) is None

    def test_laps_to_flag_lap_race(self):
        session = SessionInfo(SESSION_RACE, total_laps=25)
        assert laps_to_flag(session, 11, 0.42, None) == pytest.approx(13.58)

    def test_laps_to_flag_timed_race_and_practice(self):
        race = SessionInfo(SESSION_RACE, time_left_ms=250000, is_timed_race=True, has_extra_lap=True)
        assert laps_to_flag(race, 3, 0.0, 100000) == pytest.approx(4.0)
        # The extra lap only applies to races.
        practice = SessionInfo(SESSION_PRACTICE, time_left_ms=250000, has_extra_lap=True)
        assert laps_to_flag(practice, 3, 0.0, 100000) == pytest.approx(3.0)

    def test_laps_to_flag_unknown(self):
        assert laps_to_flag(SessionInfo(SESSION_HOTLAP, time_left_ms=9e9), 3, 0.5, 100000) is None
        assert laps_to_flag(SessionInfo(SESSION_PRACTICE, time_left_ms=0), 3, 0.5, 100000) is None
        assert laps_to_flag(SessionInfo(SESSION_RACE, total_laps=25), 3, None, None) is None
        assert laps_to_flag(None, 3, 0.5, 100000) is None

    def test_surplus_to_flag(self):
        assert surplus_to_flag(51.8, 13.58, 4.11) == pytest.approx(-4.01, abs=0.01)
        assert surplus_to_flag(51.8, None, 4.11) is None
        assert surplus_to_flag(51.8, 13.58, None) is None

    def test_target_per_lap_is_measured_from_lap_start(self):
        # 54.5 L at the line with 14 laps to go; now 42% into the lap.
        assert target_per_lap(54.5, 13.58, 0.42) == pytest.approx(54.5 / 14)
        assert target_per_lap(54.5, 0.0, 0.0) is None
        assert target_per_lap(None, 13.58, 0.42) is None

    def test_lap_budget_delta(self):
        # Target 4 L/lap, even burn, half way round: budget is 2 L.
        assert lap_budget_delta(2.1, 4.0, 0.5, None) == pytest.approx(0.1)
        assert lap_budget_delta(1.9, 4.0, 0.5, None) == pytest.approx(-0.1)
        assert lap_budget_delta(1.9, None, 0.5, None) is None

    def test_lap_budget_delta_follows_the_reference_profile(self):
        profile = [0.0, 0.75, 1.0]  # 75% of the fuel goes in the first half
        assert lap_budget_delta(3.0, 4.0, 0.5, profile) == pytest.approx(0.0)


class TestStatuses:
    @pytest.mark.parametrize("surplus, expected", [
        (5.0, STATUS_GOOD),
        (4.0, STATUS_GOOD),   # exactly one lap spare
        (3.9, STATUS_WARN),
        (0.0, STATUS_WARN),
        (-0.1, STATUS_BAD),
        (None, None),
    ])
    def test_surplus_status(self, surplus, expected):
        assert surplus_status(surplus, 4.0) == expected

    @pytest.mark.parametrize("delta, expected", [
        (-0.2, STATUS_GOOD),
        (0.0, STATUS_GOOD),
        (0.08, STATUS_WARN),  # 2% of a 4 L target
        (0.09, STATUS_BAD),
        (None, None),
    ])
    def test_lap_budget_status(self, delta, expected):
        assert lap_budget_status(delta, 4.0) == expected
