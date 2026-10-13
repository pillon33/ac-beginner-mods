import pytest

from driving import drive, drive_lap, flying_laps, state_on_flying_lap
from pitwall_core.display import STATUS_BAD, STATUS_GOOD, STATUS_WARN
from pitwall_core.fuel import (
    EXCLUDED_REFUEL, PROFILE_BUCKETS, FuelTracker, build_profile, lap_budget_delta,
    lap_budget_status, laps_of_fuel, profile_share, surplus_status, surplus_to_flag,
    target_per_lap,
)
from pitwall_core.laps import EXCLUDED_FIRST_LAP, EXCLUDED_PARTIAL, EXCLUDED_PIT
from pitwall_core.state import RaceState


class TestFuelTracking:
    def test_everything_is_empty_before_the_first_sample(self):
        fuel = RaceState().fuel
        assert fuel.fuel is None
        assert fuel.current_lap_used is None
        assert fuel.last_lap is None
        assert fuel.average_used is None

    def test_current_lap_counts_from_the_first_sample(self):
        state = RaceState()
        drive(state, [(50.0, 4, False), (49.25, 4, False)])
        assert state.fuel.fuel == 49.25
        assert state.fuel.current_lap_used == pytest.approx(0.75)

    def test_partial_lap_is_measured_but_not_averaged(self):
        state = RaceState()
        closed = drive(state, [(60.0, 2, False), (58.5, 3, False)])
        assert closed[0].excluded_reason == EXCLUDED_PARTIAL
        assert closed[0].fuel_used == pytest.approx(1.5)
        assert state.fuel.average_used is None

    def test_first_lap_is_measured_but_not_averaged(self):
        closed = drive(RaceState(), [(60.0, 0, False), (57.0, 0, False), (55.7, 1, False)])
        assert closed[0].excluded_reason == EXCLUDED_FIRST_LAP
        assert closed[0].fuel_used == pytest.approx(4.3)

    def test_clean_lap_counts_towards_average(self):
        state = state_on_flying_lap()
        flying_laps(state, 58.5, 3, [4.1])
        assert state.fuel.last_lap.fuel_used == pytest.approx(4.1)
        assert state.fuel.last_lap.is_valid
        assert state.fuel.average_used == pytest.approx(4.1)

    def test_current_lap_resets_on_the_line(self):
        assert state_on_flying_lap().fuel.current_lap_used == 0.0

    def test_pit_lane_lap_is_excluded(self):
        state = state_on_flying_lap()
        closed = drive(state, [(56.0, 3, False), (55.0, 3, True), (54.5, 4, False)])
        assert closed[0].excluded_reason == EXCLUDED_PIT
        assert state.fuel.average_used is None

    def test_refuel_is_excluded_and_current_lap_restarts_from_new_level(self):
        state = state_on_flying_lap()
        drive(state, [(57.0, 3, True), (80.0, 3, True)])
        assert state.fuel.current_lap_used == 0.0

        closed = drive(state, [(77.0, 4, False)])
        assert closed[0].excluded_reason == EXCLUDED_REFUEL
        assert closed[0].fuel_used == pytest.approx(3.0)

    def test_small_upward_noise_is_not_a_refuel(self):
        closed = drive(state_on_flying_lap(), [(56.0, 3, False), (56.05, 3, False), (54.4, 4, False)])
        assert closed[0].is_valid

    def test_fuel_used_never_negative(self):
        closed = drive(state_on_flying_lap(), [(58.55, 4, False)])
        assert closed[0].fuel_used >= 0.0

    def test_session_restart_resets_fuel_history(self):
        state = state_on_flying_lap()
        flying_laps(state, 58.5, 3, [4.0, 4.0])
        drive(state, [(60.0, 0, False)])
        assert state.fuel.average_used is None
        assert state.fuel.last_lap is None
        assert state.fuel.fuel == 60.0
        assert state.fuel.current_lap_used == 0.0


class TestAverage:
    def test_average_uses_only_the_last_five_valid_laps(self):
        state = state_on_flying_lap()
        flying_laps(state, 58.5, 3, [9.0, 4.0, 4.0, 4.2, 4.2, 4.1])
        assert state.fuel.average_lap_count == 5
        assert state.fuel.average_used == pytest.approx(4.1)

    def test_excluded_laps_do_not_dilute_the_average(self):
        state = state_on_flying_lap()
        fuel = flying_laps(state, 58.5, 3, [4.0])
        drive(state, [(fuel - 1, 4, True), (fuel - 6, 5, False)])
        flying_laps(state, fuel - 6, 5, [4.2])
        assert state.fuel.average_lap_count == 2
        assert state.fuel.average_used == pytest.approx(4.1)

    def test_window_is_configurable(self):
        state = RaceState()
        state.fuel = FuelTracker(average_window=2)
        drive(state, [(60.0, 2, False), (59.0, 3, False)])
        flying_laps(state, 59.0, 3, [5.0, 4.0, 3.0])
        assert state.fuel.average_used == pytest.approx(3.5)


class TestReferenceProfile:
    def test_valid_lap_becomes_the_reference_profile(self):
        state = state_on_flying_lap()
        assert state.fuel.reference_profile is None
        drive_lap(state, 58.5, 3, 4.0)
        profile = state.fuel.reference_profile
        assert len(profile) == PROFILE_BUCKETS + 1
        assert profile[0] == 0.0 and profile[-1] == 1.0
        assert profile_share(profile, 0.5) == pytest.approx(0.5, abs=0.03)

    def test_excluded_lap_does_not_replace_the_profile(self):
        state = state_on_flying_lap()
        drive_lap(state, 58.5, 3, 4.0)
        before = state.fuel.reference_profile
        drive(state, [(54.0, 4, True, 0.5), (53.0, 5, False, 0.0)])
        assert state.fuel.reference_profile is before

    def test_build_profile_follows_uneven_burn(self):
        # The first half of the lap burns 3 of the 4 litres.
        samples = ([3.0 * (i + 1) / 25 for i in range(25)]
                   + [3.0 + (i + 1) / 25 for i in range(25)])
        assert profile_share(build_profile(samples, 4.0), 0.5) == pytest.approx(0.75)

    def test_build_profile_fills_gaps_and_never_decreases(self):
        assert build_profile([None, 1.0, None, 0.5, 2.0], 2.0) == [0.0, 0.0, 0.5, 0.5, 0.5, 1.0]

    def test_build_profile_rejects_sparse_or_empty_laps(self):
        assert build_profile([None] * 10 + [1.0], 1.0) is None
        assert build_profile([1.0] * 10, 0.0) is None

    def test_profile_share_without_profile_is_linear(self):
        assert profile_share(None, 0.3) == 0.3
        assert profile_share(None, 1.5) == 1.0


class TestStrategyMaths:
    def test_laps_of_fuel(self):
        assert laps_of_fuel(51.8, 4.11) == pytest.approx(12.6, abs=0.01)
        assert laps_of_fuel(51.8, None) is None
        assert laps_of_fuel(51.8, 0.0) is None

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
