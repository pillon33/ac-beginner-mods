import pytest

from pitwall_core.display import (
    BOX_GOOD_MS, BOX_WARN_MS, STATUS_BAD, STATUS_BEST, slice_status, STATUS_GOOD, STATUS_WARN, delta_status, format_delta, format_lap_time,
)
from pitwall_core.sectors import MINI_SECTORS, MiniSectorTracker, build_reference, interpolate
from pitwall_core.state import Frame, RaceState
from pitwall_core.windows import time_boxes, time_readout

N = MINI_SECTORS
STEPS = 5            # frames per mini-sector
EVEN = [4500] * N    # 90 s lap


def lap_frames(times, pit_from=None, steps=STEPS):
    """One lap of (pit, position, lap_time_ms) frames: the car moves at
    constant speed through each mini-sector, times[i] ms for slice i,
    and is in the pit lane from slice `pit_from` on."""
    elapsed = 0
    for index, ms in enumerate(times):
        for k in range(steps):
            yield (pit_from is not None and index >= pit_from,
                   (index + k / float(steps)) / len(times),
                   elapsed + ms * k / float(steps))
        elapsed += ms


def feed(tracker, frames):
    for pit, position, lap_time in frames:
        tracker.update(pit, position, lap_time)


def with_reference(times=EVEN):
    """Partial first lap (slice 0 is unwatched), one full lap, then
    the first frame of a third: bests and reference are in place."""
    tracker = MiniSectorTracker()
    feed(tracker, lap_frames(times))
    feed(tracker, lap_frames(times))
    feed(tracker, [(False, 0.0, 0)])
    return tracker


def test_no_data_means_no_theoretical_best_or_delta():
    tracker = MiniSectorTracker()
    tracker.update(False, None, None)
    tracker.update(False, 0.5, None)
    assert tracker.theoretical_best_ms is None
    assert tracker.delta_ms is None


def test_first_partial_lap_cannot_complete_the_reference():
    tracker = MiniSectorTracker()
    feed(tracker, lap_frames(EVEN))
    feed(tracker, [(False, 0.0, 0)])
    # Slice 0 was where we joined: not watched from its start.
    assert sorted(tracker.best_ms) == list(range(1, N))
    assert tracker.theoretical_best_ms is None


def test_mini_sector_bests_and_theoretical_best():
    times = [4000 + 100 * i for i in range(N)]
    tracker = with_reference(times)
    assert [tracker.best_ms[i] for i in range(N)] == pytest.approx(times)
    assert tracker.theoretical_best_ms == pytest.approx(sum(times))


def test_mini_times_are_interpolated_between_sparse_frames():
    times = [4500] * N   # constant speed: interpolation is exact
    tracker = MiniSectorTracker()
    # Frames only every 1.5 slices: boundaries are never sampled.
    sparse = lambda: list(lap_frames(times, steps=2))[::3]
    feed(tracker, sparse())
    feed(tracker, sparse())
    feed(tracker, [(False, 0.0, 0)])
    for index, best in tracker.best_ms.items():
        assert abs(best - times[index]) < 1


def test_best_of_each_mini_sector_across_laps():
    tracker = with_reference()
    lap2 = list(EVEN)
    lap2[3] = 4300
    lap2[7] = 4800
    feed(tracker, lap_frames(lap2))
    feed(tracker, [(False, 0.0, 0)])
    assert tracker.best_ms[3] == pytest.approx(4300)
    assert tracker.best_ms[7] == pytest.approx(4500)
    assert tracker.theoretical_best_ms == pytest.approx(89800)


def test_reference_ends_at_the_theoretical_best():
    tracker = with_reference([4000 + 100 * i for i in range(N)])
    reference = build_reference(tracker.best_trace, tracker.best_ms, N)
    assert reference[0] == (0.0, 0)
    assert reference[-1][0] == 1.0
    assert reference[-1][1] == tracker.theoretical_best_ms
    assert all(a[0] <= b[0] and a[1] <= b[1] for a, b in zip(reference, reference[1:]))


def test_no_delta_without_a_full_reference():
    tracker = MiniSectorTracker()
    for _ in range(1):
        for pit, position, lap_time in lap_frames(EVEN):
            tracker.update(pit, position, lap_time)
            assert tracker.delta_ms is None


def test_delta_updates_every_frame_mid_slice():
    tracker = with_reference()
    # Lose 1 s in slice 2 only, with a frame every fifth of a slice.
    times = list(EVEN)
    times[2] = 5500
    deltas = []
    for pit, position, lap_time in lap_frames(times, steps=10):
        tracker.update(pit, position, lap_time)
        deltas.append(tracker.delta_ms)
    assert all(d is not None for d in deltas)
    slice2 = deltas[20:30]
    assert slice2 == sorted(slice2) and len(set(slice2)) == 10   # grows each frame
    assert abs(slice2[5] - 500) < 1
    assert abs(deltas[-1] - 1000) < 1


def test_delta_goes_negative_when_faster_than_the_reference():
    tracker = with_reference()
    times = list(EVEN)
    times[1] = 4000
    deltas = []
    for pit, position, lap_time in lap_frames(times):
        tracker.update(pit, position, lap_time)
        deltas.append(tracker.delta_ms)
    assert deltas[2 * STEPS] < -499
    assert deltas[-1] < -499


def test_delta_interpolates_between_reference_points():
    tracker = with_reference()
    (p0, t0), (p1, t1) = tracker._reference[10], tracker._reference[11]
    position = p0 + 0.4 * (p1 - p0)
    tracker._prev = (position - 0.01, 0)
    tracker.update(False, position, t0 + 0.4 * (t1 - t0) + 250)
    assert abs(tracker.delta_ms - 250) < 0.001


def test_interpolate_clamps_and_handles_empty():
    points = [(0.0, 0), (0.5, 1000), (1.0, 3000)]
    assert interpolate([], 0.3) is None
    assert interpolate(points, -0.1) == 0
    assert interpolate(points, 0.25) == 500
    assert interpolate(points, 0.75) == 2000
    assert interpolate(points, 1.2) == 3000


def test_delta_continues_through_the_start_finish_wrap():
    tracker = with_reference()
    seen = []
    for pit, position, lap_time in lap_frames(EVEN):
        tracker.update(pit, position, lap_time)
        seen.append(tracker.delta_ms)
    tracker.update(False, 0.0, 0)          # new lap
    seen.append(tracker.delta_ms)
    tracker.update(False, 0.01, 900)
    seen.append(tracker.delta_ms)
    assert all(d is not None and abs(d) < 1 for d in seen)


def test_reference_is_frozen_mid_lap_and_promoted_at_the_line():
    tracker = with_reference()
    frozen = tracker._reference
    faster = list(EVEN)
    faster[3] = 4000                       # a new best, set mid-lap
    deltas = []
    for pit, position, lap_time in lap_frames(faster):
        tracker.update(pit, position, lap_time)
        # Same reference object, same theoretical best, the whole lap.
        assert tracker._reference is frozen
        assert tracker.theoretical_best_ms == pytest.approx(90000)
        deltas.append(tracker.delta_ms)
    # Compared against the old reference: 0.5 s ahead from slice 3 on.
    assert abs(deltas[-1] + 500) < 1
    assert tracker.best_ms[3] == pytest.approx(4500)      # nothing merged before the line
    tracker.update(False, 0.0, 0)
    assert tracker._reference is not frozen
    assert tracker.best_ms[3] == pytest.approx(4000)
    assert tracker.theoretical_best_ms == pytest.approx(89500)
    # The new lap's delta uses the promoted reference.
    assert abs(tracker.delta_ms) < 1


def test_pit_lane_lap_does_not_poison_the_reference():
    tracker = with_reference()
    frozen = tracker._reference
    # Quick-looking slices, but the car is in the pit lane from slice 10.
    fast = [1000] * N
    deltas = []
    for pit, position, lap_time in lap_frames(fast, pit_from=10):
        tracker.update(pit, position, lap_time)
        deltas.append(tracker.delta_ms)
    assert all(d is None for d in deltas[10 * STEPS:])
    tracker.update(False, 0.0, 0)
    assert tracker._reference is frozen
    assert tracker.best_ms == pytest.approx({i: 4500 for i in range(N)})
    assert tracker.theoretical_best_ms == pytest.approx(90000)
    # The next clean lap has a delta again.
    tracker.update(False, 0.01, 900)
    assert abs(tracker.delta_ms) < 1


def test_position_going_backwards_blanks_the_delta_and_the_lap():
    tracker = with_reference()
    frames_ = list(lap_frames([4000] * N))
    feed(tracker, frames_[:30])
    assert tracker.delta_ms is not None
    tracker.update(False, 0.1, 30000)       # spun back
    assert tracker.delta_ms is None
    feed(tracker, frames_[40:])
    assert tracker.delta_ms is None
    tracker.update(False, 0.0, 0)
    assert tracker.theoretical_best_ms == pytest.approx(90000)   # lap discarded
    assert tracker.best_ms[0] == pytest.approx(4500)


def test_position_jump_blanks_the_delta():
    tracker = with_reference()
    feed(tracker, list(lap_frames(EVEN))[:10])
    assert tracker.delta_ms is not None
    tracker.update(False, 0.6, 50000)       # teleported
    assert tracker.delta_ms is None


def test_joining_mid_lap_counts_only_slices_watched_from_their_start():
    tracker = MiniSectorTracker()
    feed(tracker, list(lap_frames(EVEN))[10 * STEPS + 2:])
    feed(tracker, [(False, 0.0, 0)])
    assert sorted(tracker.best_ms) == list(range(11, N))


def test_trace_memory_is_bounded():
    tracker = MiniSectorTracker(count=1)
    tracker.update(False, 0.0, 0)
    tracker.update(False, 0.001, 10)
    for k in range(2, 3000):
        tracker.update(False, 0.9 * k / 3000.0, k * 10)
    assert len(tracker._trace) <= 400


def test_session_restart_forgets_everything():
    tracker = with_reference()
    assert tracker.theoretical_best_ms == pytest.approx(90000)
    tracker.update(False, 0.0, 0, restarted=True)
    assert tracker.best_ms == {}
    assert tracker.best_trace == {}
    assert tracker.delta_ms is None
    assert tracker.theoretical_best_ms is None


def stream_state(laps=2, extra=()):
    state = RaceState()
    count = 0
    for lap in range(laps):
        for pit, position, lap_time in lap_frames(EVEN):
            state.update(Frame(fuel=50.0, completed_laps=lap, in_pit_lane=pit,
                               lap_progress=position, lap_time_ms=lap_time))
    state.update(Frame(fuel=50.0, completed_laps=laps, in_pit_lane=False,
                       lap_progress=0.0, lap_time_ms=0))
    return state


def test_race_state_resets_sectors_when_the_lap_counter_drops():
    state = stream_state()
    assert state.sectors.theoretical_best_ms == pytest.approx(90000)
    state.update(Frame(fuel=50.0, completed_laps=0, in_pit_lane=False, lap_progress=0.0,
                       lap_time_ms=0))
    assert state.sectors.best_ms == {}
    assert state.sectors.delta_ms is None


def test_time_readout_shows_dashes_until_a_theoretical_best_exists():
    state = stream_state(laps=1)
    assert time_readout(state)["theoretical"] == ("--", None)
    assert time_readout(state)["delta"] == ("--", None)


def test_time_readout_lap_timer_without_sector_data():
    state = RaceState()
    state.update(Frame(fuel=50.0, completed_laps=0, in_pit_lane=False, lap_time_ms=65432))
    assert time_readout(state)["lap"] == ("1:05.432", None)
    assert time_readout(state)["delta"] == ("--", None)


def test_time_readout_signed_delta_and_status():
    state = stream_state()
    assert time_readout(state)["theoretical"] == ("1:30.000", None)
    assert time_readout(state)["delta"] == ("+0.000", STATUS_GOOD)

    def at(position, lap_ms):
        state.update(Frame(fuel=50.0, completed_laps=2, in_pit_lane=False,
                           lap_progress=position, lap_time_ms=lap_ms))
        return time_readout(state)["delta"]

    # Reference pace at 0.1 of the lap is 9000 ms.
    assert at(0.08, 7200 + 300) == ("+0.300", STATUS_WARN)
    assert at(0.09, 8100 + 2000) == ("+2.000", STATUS_BAD)
    assert at(0.10, 9000 - 123) == ("-0.123", STATUS_GOOD)


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


# --- mini-sector boxes -------------------------------------------

def test_slice_status_thresholds():
    assert slice_status(None) is None
    assert slice_status(-1) == STATUS_BEST
    assert slice_status(0) == STATUS_GOOD
    assert slice_status(BOX_GOOD_MS) == STATUS_GOOD
    assert slice_status(BOX_GOOD_MS + 1) == STATUS_WARN
    assert slice_status(BOX_WARN_MS) == STATUS_WARN
    assert slice_status(BOX_WARN_MS + 1) == STATUS_BAD


def drive_lap(tracker, times):
    feed(tracker, lap_frames(times))


def test_boxes_are_empty_before_any_reference():
    tracker = MiniSectorTracker()
    drive_lap(tracker, EVEN)
    assert tracker.slice_statuses == [None] * N


def test_boxes_fill_in_as_the_lap_progresses_and_grade_each_slice():
    tracker = with_reference()
    times = list(EVEN)
    times[2] = 4400    # 100 ms quicker: purple
    times[3] = 4530    # +30 ms: green
    times[4] = 4650    # +150 ms: yellow
    times[5] = 4900    # +400 ms: red
    feed(tracker, list(lap_frames(times))[:7 * STEPS])
    statuses = tracker.slice_statuses
    assert statuses[:2] == [STATUS_GOOD] * 2
    assert statuses[2:6] == [STATUS_BEST, STATUS_GOOD, STATUS_WARN, STATUS_BAD]
    assert statuses[7:] == [None] * (N - 7)     # not driven yet


def test_boxes_use_the_frozen_reference_mid_lap():
    tracker = with_reference()
    times = list(EVEN)
    times[1] = 4000
    times[2] = 4000
    feed(tracker, list(lap_frames(times))[:4 * STEPS])
    # Slice 2 is again quicker than the reference: still purple, not
    # compared against slice 1's new (pending) best or its own.
    assert tracker.slice_statuses[1:3] == [STATUS_BEST, STATUS_BEST]


def test_finished_lap_boxes_stay_until_the_next_laps_first_slice_completes():
    tracker = with_reference()
    times = list(EVEN)
    times[6] = 5000
    drive_lap(tracker, times)
    tracker.update(False, 0.0, 0)           # the line
    held = tracker.slice_statuses
    assert held[6] == STATUS_BAD and held.count(None) == 0
    # Part way through the first slice: still the finished lap.
    new_lap = list(lap_frames(EVEN))
    feed(tracker, new_lap[1:3])
    assert tracker.slice_statuses == held
    # First slice done: boxes switch to the new lap.
    feed(tracker, new_lap[3:STEPS + 2])
    fresh = tracker.slice_statuses
    assert fresh[0] is not None and fresh[1:] == [None] * (N - 1)


def test_pit_lap_leaves_untouched_slices_empty():
    tracker = with_reference()
    feed(tracker, lap_frames(EVEN, pit_from=10))
    assert tracker.slice_statuses[:9].count(None) == 0
    assert tracker.slice_statuses[10:] == [None] * (N - 10)


def test_restart_clears_the_boxes():
    tracker = with_reference()
    drive_lap(tracker, EVEN)
    assert any(tracker.slice_statuses)
    tracker.update(False, 0.0, 0, restarted=True)
    assert tracker.slice_statuses == [None] * N


def test_time_boxes_reads_the_tracker():
    state = stream_state()
    assert time_boxes(state) == state.sectors.slice_statuses
    assert len(time_boxes(state)) == N
