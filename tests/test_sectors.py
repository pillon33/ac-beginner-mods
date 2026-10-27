from pitwall_core.display import (
    STATUS_BAD, STATUS_GOOD, STATUS_WARN, delta_status, format_delta, format_lap_time,
)
from pitwall_core.sectors import SectorTracker
from pitwall_core.state import Frame, RaceState
from pitwall_core.windows import time_readout


def sample(tracker, sector, last_ms=None, pit=False, laps=1, count=3, restarted=False):
    tracker.update(sector, last_ms, pit, laps, count, restarted)


def run_lap(tracker, times, laps=1, start_sector=0, pit_in=None):
    """Cross each sector boundary in turn: times[i] is sector i's time.
    Ends in the next lap's sector 0 (when all sectors are driven)."""
    for index, ms in enumerate(times):
        nxt = (start_sector + index + 1) % len(times)
        sample(tracker, nxt, ms, pit=(pit_in == index), laps=laps + (1 if nxt == 0 else 0))


def tracker_in_sector_0_watched():
    """Joined in sector 2, crossed the line: now watching a full lap."""
    tracker = SectorTracker()
    sample(tracker, 2, laps=1)
    sample(tracker, 0, 40000, laps=2)  # mid-sector join: not counted
    return tracker


def test_no_sector_data_means_no_theoretical_best():
    tracker = SectorTracker()
    sample(tracker, None)
    assert tracker.theoretical_best_ms is None
    assert tracker.delta_ms is None


def test_joining_mid_sector_does_not_count_that_sector():
    tracker = tracker_in_sector_0_watched()
    assert tracker.best_ms == {}


def test_theoretical_best_needs_every_sector():
    tracker = tracker_in_sector_0_watched()
    sample(tracker, 1, 30000, laps=2)
    sample(tracker, 2, 31000, laps=2)
    assert tracker.best_ms == {0: 30000, 1: 31000}
    assert tracker.theoretical_best_ms is None
    sample(tracker, 0, 29000, laps=3)
    assert tracker.theoretical_best_ms == 90000


def test_unknown_sector_count_gives_no_theoretical_best():
    tracker = SectorTracker()
    for sector, ms in [(2, None), (0, 1), (1, 30000), (2, 31000), (0, 29000)]:
        tracker.update(sector, ms, False, 2, None)
    assert tracker.theoretical_best_ms is None


def test_theoretical_best_combines_best_sectors_from_different_laps():
    tracker = tracker_in_sector_0_watched()
    run_lap(tracker, [30000, 31000, 29000], laps=2)
    run_lap(tracker, [30500, 30000, 29500], laps=3)
    assert tracker.best_ms == {0: 30000, 1: 30000, 2: 29000}
    assert tracker.theoretical_best_ms == 89000


def test_delta_is_gap_to_best_sectors_so_far_and_holds_across_the_line():
    tracker = tracker_in_sector_0_watched()
    run_lap(tracker, [30000, 31000, 29000], laps=2)
    assert tracker.delta_ms == 0          # lap that set every best
    sample(tracker, 1, 30400, laps=3)
    assert tracker.delta_ms == 400
    sample(tracker, 2, 31100, laps=3)
    assert tracker.delta_ms == 400 + 100
    sample(tracker, 0, 29200, laps=4)
    assert tracker.delta_ms == 700        # full lap gap, held into the next lap
    sample(tracker, 0, None, laps=4)
    assert tracker.delta_ms == 700


def test_pit_lane_sector_is_not_counted_and_blanks_the_lap_delta():
    tracker = tracker_in_sector_0_watched()
    run_lap(tracker, [30000, 31000, 29000], laps=2)
    # Out-lap: in the pit lane through sector 0, which is not counted.
    sample(tracker, 0, 29000, pit=True, laps=3)
    sample(tracker, 1, 20000, pit=True, laps=3)
    assert tracker.best_ms[0] == 30000
    assert tracker.delta_ms is None
    # Sector 1 was entered from the pit lane, so it isn't counted either.
    sample(tracker, 2, 20000, laps=3)
    assert tracker.best_ms[1] == 31000
    # Later clean sectors still count towards bests but the lap has no delta.
    assert tracker.delta_ms is None
    sample(tracker, 0, 28000, laps=4)
    assert tracker.best_ms[2] == 28000
    assert tracker.delta_ms is None
    # Next lap is clean again.
    sample(tracker, 1, 30000, laps=4)
    assert tracker.delta_ms == 0


def test_pit_visit_in_the_sector_start_taints_it():
    tracker = tracker_in_sector_0_watched()
    sample(tracker, 1, 30000, laps=2)
    sample(tracker, 1, None, pit=True, laps=2)
    sample(tracker, 2, 5000, laps=2)
    assert 1 not in tracker.best_ms


def test_standing_start_sector_is_not_counted():
    tracker = SectorTracker()
    sample(tracker, 0, laps=0)
    sample(tracker, 1, 45000, laps=0)
    assert tracker.best_ms == {}
    sample(tracker, 2, 31000, laps=0)
    assert tracker.best_ms == {1: 31000}


def test_invalid_or_zero_sector_times_are_ignored():
    tracker = tracker_in_sector_0_watched()
    sample(tracker, 1, 0, laps=2)
    sample(tracker, 2, None, laps=2)
    assert tracker.best_ms == {}


def test_skipped_sector_is_not_counted():
    tracker = tracker_in_sector_0_watched()
    sample(tracker, 2, 30000, laps=2)   # 0 -> 2 skips sector 1
    assert tracker.best_ms == {}


def test_session_restart_forgets_everything():
    tracker = tracker_in_sector_0_watched()
    run_lap(tracker, [30000, 31000, 29000], laps=2)
    assert tracker.theoretical_best_ms == 90000
    sample(tracker, 0, None, laps=0, restarted=True)
    assert tracker.best_ms == {}
    assert tracker.delta_ms is None
    assert tracker.theoretical_best_ms is None


def test_race_state_resets_sectors_when_the_lap_counter_drops():
    state = RaceState()

    def frame(laps, sector, last_ms=None):
        state.update(Frame(fuel=50.0, completed_laps=laps, in_pit_lane=False,
                           current_sector=sector, last_sector_ms=last_ms, sector_count=3))

    frame(2, 2)
    for laps, sector, ms in [(3, 0, 1), (3, 1, 30000), (3, 2, 31000), (4, 0, 29000)]:
        frame(laps, sector, ms)
    assert state.sectors.theoretical_best_ms == 90000
    frame(0, 0)
    assert state.sectors.best_ms == {}


def make_state(sectors_done=3, lap_time_ms=12345):
    state = RaceState()

    def frame(laps, sector, last_ms=None, lap_ms=None):
        state.update(Frame(fuel=50.0, completed_laps=laps, in_pit_lane=False,
                           lap_time_ms=lap_ms, current_sector=sector, last_sector_ms=last_ms,
                           sector_count=3))

    frame(2, 2)
    steps = [(3, 0, 1), (3, 1, 30000), (3, 2, 31000), (4, 0, 29000)][:sectors_done + 1]
    for laps, sector, ms in steps:
        frame(laps, sector, ms)
    frame(steps[-1][0], steps[-1][1], None, lap_time_ms)
    return state, frame


def test_time_readout_shows_dashes_until_a_theoretical_best_exists():
    state, _ = make_state(sectors_done=2, lap_time_ms=None)
    assert time_readout(state) == {
        "lap": ("--", None), "theoretical": ("--", None), "delta": ("--", None)}


def test_time_readout_shows_timer_even_before_sectors():
    state = RaceState()
    state.update(Frame(fuel=50.0, completed_laps=0, in_pit_lane=False, lap_time_ms=65432))
    assert time_readout(state)["lap"] == ("1:05.432", None)


def test_time_readout_with_theoretical_best_and_delta():
    state, frame = make_state(lap_time_ms=12345)
    readout = time_readout(state)
    assert readout["lap"] == ("12.345", None)
    assert readout["theoretical"] == ("1:30.000", None)
    assert readout["delta"] == ("+0.000", STATUS_GOOD)
    frame(4, 1, 30400, 31000)
    assert time_readout(state)["delta"] == ("+0.400", STATUS_WARN)
    frame(4, 2, 32000, 62000)
    assert time_readout(state)["delta"] == ("+1.400", STATUS_BAD)


def test_formatting_and_status():
    assert format_lap_time(None) == "--"
    assert format_lap_time(83456) == "1:23.456"
    assert format_lap_time(60000) == "1:00.000"
    assert format_lap_time(5007) == "5.007"
    assert format_delta(None) == "--"
    assert format_delta(-1050) == "-1.050"
    assert delta_status(None) is None
    assert delta_status(0) == STATUS_GOOD
    assert delta_status(500) == STATUS_WARN
    assert delta_status(501) == STATUS_BAD
