from pitwall_core.display import (
    STATUS_BAD, STATUS_GOOD, STATUS_WARN, delta_status, format_delta, format_lap_time,
)
from pitwall_core.sectors import SectorTracker, build_reference, interpolate
from pitwall_core.state import Frame, RaceState
from pitwall_core.windows import time_readout


STEPS = 20  # frames per sector


def frames(times, laps, pit_in=None, first_last_ms=None):
    """One lap of per-frame samples for a 3-sector track whose sector
    boundaries are at 0, 1/3, 2/3 of the lap. times[i] is sector i's
    time; the car moves at constant speed within a sector. Yields
    (sector, last_sector_ms, pit, completed_laps, position, lap_time_ms)."""
    elapsed = 0
    count = len(times)
    for index, ms in enumerate(times):
        last = first_last_ms if index == 0 else times[index - 1]
        for k in range(STEPS):
            position = (index + k / float(STEPS)) / count
            yield (index, last if k == 0 else None, pit_in == index, laps,
                   position, elapsed + ms * k / float(STEPS))
        elapsed += ms


def feed(tracker, sample, count=3, restarted=False):
    sector, last_ms, pit, laps, position, lap_ms = sample
    tracker.update(sector, last_ms, pit, laps, count, restarted, position, lap_ms)


def run_lap(tracker, times, laps=2, **kwargs):
    for sample in frames(times, laps, **kwargs):
        feed(tracker, sample)


def tracker_after_join(times=(30000, 31000, 29000)):
    """Joined mid-lap in sector 2, then drove one full clean lap:
    every best is set, the reference is that lap."""
    tracker = SectorTracker()
    feed(tracker, (2, None, False, 1, 0.97, 87000))
    run_lap(tracker, times, laps=2, first_last_ms=29000)
    # Cross the line so the last sector is closed.
    feed(tracker, (0, times[2], False, 3, 0.0, 0))
    return tracker


def test_no_sector_data_means_no_theoretical_best():
    tracker = SectorTracker()
    tracker.update(None, None, False, 0)
    assert tracker.theoretical_best_ms is None
    assert tracker.delta_ms is None


def test_joining_mid_sector_does_not_count_that_sector():
    tracker = SectorTracker()
    feed(tracker, (2, None, False, 1, 0.97, 87000))
    feed(tracker, (0, 29000, False, 2, 0.0, 0))
    assert tracker.best_ms == {}


def test_theoretical_best_needs_every_sector():
    tracker = SectorTracker()
    feed(tracker, (2, None, False, 1, 0.97, 87000))
    for sample in frames([30000, 31000, 29000], 2, first_last_ms=29000):
        feed(tracker, sample)
    # Sector 2 is still being driven.
    assert sorted(tracker.best_ms) == [0, 1]
    assert tracker.theoretical_best_ms is None
    feed(tracker, (0, 29000, False, 3, 0.0, 0))
    assert tracker.theoretical_best_ms == 90000


def test_unknown_sector_count_gives_no_theoretical_best_or_delta():
    tracker = SectorTracker()
    for sample in frames([30000, 31000, 29000], 2, first_last_ms=29000):
        tracker.update(sample[0], sample[1], sample[2], sample[3], None, False, sample[4], sample[5])
    assert tracker.theoretical_best_ms is None
    assert tracker.delta_ms is None


def test_theoretical_best_combines_best_sectors_from_different_laps():
    tracker = tracker_after_join()
    run_lap(tracker, [30500, 30000, 29500], laps=3, first_last_ms=29000)
    feed(tracker, (0, 29500, False, 4, 0.0, 0))
    assert tracker.best_ms == {0: 30000, 1: 30000, 2: 29000}
    assert tracker.theoretical_best_ms == 89000


def test_reference_ends_at_the_theoretical_best():
    tracker = tracker_after_join()
    run_lap(tracker, [30500, 30000, 29500], laps=3, first_last_ms=29000)
    feed(tracker, (0, 29500, False, 4, 0.0, 0))
    reference = build_reference(tracker.best_trace, tracker.best_ms, 3)
    assert reference[0] == (0.0, 0)
    assert reference[-1] == (1.0, tracker.theoretical_best_ms)
    assert all(a[0] <= b[0] and a[1] <= b[1] for a, b in zip(reference, reference[1:]))


def test_no_delta_without_a_full_reference():
    tracker = SectorTracker()
    feed(tracker, (2, None, False, 1, 0.97, 87000))
    for sample in frames([30000, 31000, 29000], 2, first_last_ms=29000):
        feed(tracker, sample)
        assert tracker.delta_ms is None


def test_delta_updates_every_frame_mid_sector():
    tracker = tracker_after_join()
    # Next lap: slower than the reference by 2 s in sector 0 only.
    deltas = []
    for sample in frames([32000, 31000, 29000], 3, first_last_ms=29000):
        feed(tracker, sample)
        deltas.append(tracker.delta_ms)
    sector0 = deltas[:STEPS]
    assert all(d is not None for d in deltas)
    # Grows steadily through sector 0, not stuck at a split.
    assert sector0 == sorted(sector0) and len(set(sector0)) == STEPS
    assert abs(sector0[10] - 1000) < 1
    # Sectors 1 and 2 are at reference pace: the lost 2 s stays.
    assert abs(deltas[STEPS + 10] - 2000) < 1
    assert abs(deltas[-1] - 2000) < 1


def test_delta_goes_negative_when_faster_than_the_reference():
    tracker = tracker_after_join()
    deltas = []
    for sample in frames([29000, 31000, 29000], 3, first_last_ms=29000):
        feed(tracker, sample)
        deltas.append(tracker.delta_ms)
    assert deltas[STEPS - 1] < -900
    # The faster sector is the new reference, so the lap ends 1 s better.
    feed(tracker, (0, 29000, False, 4, 0.0, 0))
    assert tracker.theoretical_best_ms == 89000


def test_delta_interpolates_between_trace_samples():
    tracker = tracker_after_join()
    reference = tracker._reference
    (p0, t0), (p1, t1) = reference[10], reference[11]
    position = p0 + 0.4 * (p1 - p0)
    lap_time = t0 + 0.4 * (t1 - t0) + 250
    tracker._last_pos = position - 0.01   # as if driving on from just before
    tracker.update(0, None, False, 3, 3, False, position, lap_time)
    assert abs(tracker.delta_ms - 250) < 0.001


def test_interpolate_clamps_and_handles_empty():
    points = [(0.0, 0), (0.5, 1000), (1.0, 3000)]
    assert interpolate([], 0.3) is None
    assert interpolate(points, -0.1) == 0
    assert interpolate(points, 0.25) == 500
    assert interpolate(points, 0.75) == 2000
    assert interpolate(points, 1.2) == 3000


def test_delta_survives_the_start_finish_wrap():
    tracker = tracker_after_join()
    for sample in frames([30000, 31000, 29000], 3, first_last_ms=29000):
        feed(tracker, sample)
        assert tracker.delta_ms is not None
        assert abs(tracker.delta_ms) < 1
    # Position wraps from ~0.98 to 0.0 and the delta carries on.
    feed(tracker, (0, 29000, False, 4, 0.0, 0))
    assert tracker.delta_ms is not None and abs(tracker.delta_ms) < 1


def test_position_wraps_before_the_sector_index():
    tracker = tracker_after_join()
    run_lap(tracker, [30000, 31000, 29000], laps=3, first_last_ms=29000)
    # Position is already past the line while the index still says sector 2.
    tracker.update(2, None, False, 4, 3, False, 0.001, 20)
    assert tracker.delta_ms is None
    feed(tracker, (0, 29000, False, 4, 0.002, 40))
    assert tracker.best_ms[2] == 29000   # the closing sector wasn't spoiled
    assert abs(tracker.delta_ms + 140) < 1   # 40 ms vs 180 ms at 0.002


def test_position_going_backwards_blanks_the_delta_until_the_line():
    tracker = tracker_after_join()
    frames_ = list(frames([30000, 31000, 29000], 3, first_last_ms=29000))
    for sample in frames_[:30]:
        feed(tracker, sample)
    assert tracker.delta_ms is not None
    feed(tracker, (1, None, False, 3, 0.2, 40000))   # spun back
    assert tracker.delta_ms is None
    for sample in frames_[30:]:
        feed(tracker, sample)
        assert tracker.delta_ms is None
    feed(tracker, (0, 29000, False, 4, 0.0, 0))
    assert abs(tracker.delta_ms) < 1


def test_position_jump_blanks_the_delta():
    tracker = tracker_after_join()
    frames_ = list(frames([30000, 31000, 29000], 3, first_last_ms=29000))
    for sample in frames_[:10]:
        feed(tracker, sample)
    feed(tracker, (1, None, False, 3, 0.45, 43000))  # teleported ahead
    assert tracker.delta_ms is None


def test_pit_lane_blanks_the_delta_for_the_rest_of_the_lap():
    tracker = tracker_after_join()
    for sample in frames([30000, 31000, 29000], 3, pit_in=1, first_last_ms=29000):
        feed(tracker, sample)
        if sample[0] >= 1:
            assert tracker.delta_ms is None
    # Clean again after the line.
    feed(tracker, (0, 29000, False, 4, 0.0, 0))
    assert abs(tracker.delta_ms) < 1


def test_pit_lane_sector_is_not_counted():
    tracker = tracker_after_join()
    run_lap(tracker, [20000, 20000, 20000], laps=3, pit_in=1, first_last_ms=29000)
    feed(tracker, (0, 20000, False, 4, 0.0, 0))
    # Entering the pit lane in sector 1 spoils sector 1, and sector 0
    # too, since it closes on the frame the car is in the pit lane.
    assert tracker.best_ms == {0: 30000, 1: 31000, 2: 20000}


def test_standing_start_sector_is_not_counted():
    tracker = SectorTracker()
    run_lap(tracker, [45000, 31000, 29000], laps=0)
    feed(tracker, (0, 29000, False, 1, 0.0, 0))
    assert tracker.best_ms == {1: 31000, 2: 29000}


def test_invalid_or_zero_sector_times_are_ignored():
    tracker = SectorTracker()
    feed(tracker, (2, None, False, 1, 0.97, 87000))
    feed(tracker, (0, 29000, False, 2, 0.0, 0))
    feed(tracker, (1, 0, False, 2, 0.34, 30000))
    feed(tracker, (2, None, False, 2, 0.67, 61000))
    assert tracker.best_ms == {}


def test_skipped_sector_is_not_counted():
    tracker = SectorTracker()
    feed(tracker, (2, None, False, 1, 0.97, 87000))
    feed(tracker, (0, 29000, False, 2, 0.0, 0))
    feed(tracker, (0, None, False, 2, 0.1, 9000))
    feed(tracker, (2, 30000, False, 2, 0.7, 60000))   # 0 -> 2 skips sector 1
    assert tracker.best_ms == {}


def test_trace_memory_is_bounded():
    tracker = SectorTracker()
    feed(tracker, (2, None, False, 1, 0.97, 87000))
    feed(tracker, (0, 29000, False, 2, 0.0, 0))
    for k in range(1, 3000):
        tracker.update(0, None, False, 2, 3, False, 0.3 * k / 3000.0, k * 10)
    assert len(tracker._trace) <= 400


def test_session_restart_forgets_everything():
    tracker = tracker_after_join()
    assert tracker.theoretical_best_ms == 90000
    tracker.update(0, None, False, 0, 3, True, 0.0, 0)
    assert tracker.best_ms == {}
    assert tracker.best_trace == {}
    assert tracker.delta_ms is None
    assert tracker.theoretical_best_ms is None


def stream_state(stream):
    state = RaceState()
    for sector, last, pit, laps, position, lap_ms in stream:
        state.update(Frame(fuel=50.0, completed_laps=laps, in_pit_lane=pit, lap_progress=position,
                           lap_time_ms=lap_ms, current_sector=sector, last_sector_ms=last,
                           sector_count=3))
    return state


def reference_stream():
    stream = [(2, None, False, 1, 0.97, 87000)]
    stream += list(frames([30000, 31000, 29000], 2, first_last_ms=29000))
    stream.append((0, 29000, False, 3, 0.0, 0))
    return stream


def test_race_state_resets_sectors_when_the_lap_counter_drops():
    state = stream_state(reference_stream())
    assert state.sectors.theoretical_best_ms == 90000
    state.update(Frame(fuel=50.0, completed_laps=0, in_pit_lane=False, lap_progress=0.0,
                       lap_time_ms=0, current_sector=0, sector_count=3))
    assert state.sectors.best_ms == {}
    assert state.sectors.delta_ms is None


def test_time_readout_shows_dashes_until_a_theoretical_best_exists():
    state = stream_state(reference_stream()[:30])
    assert time_readout(state)["theoretical"] == ("--", None)
    assert time_readout(state)["delta"] == ("--", None)


def test_time_readout_lap_timer_without_sector_data():
    state = RaceState()
    state.update(Frame(fuel=50.0, completed_laps=0, in_pit_lane=False, lap_time_ms=65432))
    assert time_readout(state)["lap"] == ("1:05.432", None)
    assert time_readout(state)["delta"] == ("--", None)


def test_time_readout_signed_delta_and_status():
    state = stream_state(reference_stream())
    assert time_readout(state)["theoretical"] == ("1:30.000", None)
    assert time_readout(state)["delta"] == ("+0.000", STATUS_GOOD)

    def at(position, lap_ms):
        state.update(Frame(fuel=50.0, completed_laps=3, in_pit_lane=False, lap_progress=position,
                           lap_time_ms=lap_ms, current_sector=0, sector_count=3))
        return time_readout(state)["delta"]

    # Reference pace at 0.1 of the lap is 9000 ms (30 s per third).
    assert at(0.1, 9000 + 300) == ("+0.300", STATUS_WARN)
    assert at(0.12, 10800 + 2000) == ("+2.000", STATUS_BAD)
    assert at(0.14, 12600 - 123) == ("-0.123", STATUS_GOOD)


def test_formatting_and_status():
    assert format_lap_time(None) == "--"
    assert format_lap_time(83456) == "1:23.456"
    assert format_lap_time(60000) == "1:00.000"
    assert format_lap_time(5007) == "5.007"
    assert format_delta(None) == "--"
    assert format_delta(-1050) == "-1.050"
    assert format_delta(250) == "+0.250"
    assert delta_status(None) is None
    assert delta_status(-400) == STATUS_GOOD
    assert delta_status(0) == STATUS_GOOD
    assert delta_status(500) == STATUS_WARN
    assert delta_status(501) == STATUS_BAD
