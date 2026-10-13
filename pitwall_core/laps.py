"""
laps.py — lap bookkeeping shared by every window: when a lap ends,
how far round the current lap the car is, lap times, and which laps
are representative.

A lap ends when AC's completed-lap counter goes up. Not every lap is
representative, so each closed lap gets an `excluded_reason` (None
means it counts towards averages):

  partial   we started watching mid-lap, or the counter skipped a lap
  first     lap 1: standing start or out-lap from the grid
  pit       the car was in the pit lane at some point

Other trackers can add reasons of their own (fuel adds "refuel").
"""

from collections import deque

DEFAULT_AVERAGE_WINDOW = 5

EXCLUDED_PARTIAL = "partial"
EXCLUDED_FIRST_LAP = "first"
EXCLUDED_PIT = "pit"


def average(values):
    values = list(values)
    if not values:
        return None
    return sum(values) / len(values)


class ClosedLap(object):
    """A lap that has just ended."""

    def __init__(self, lap_number, excluded_reason=None, lap_time_ms=None):
        self.lap_number = lap_number
        self.excluded_reason = excluded_reason
        self.lap_time_ms = lap_time_ms

    @property
    def is_valid(self):
        return self.excluded_reason is None

    def __repr__(self):
        return "ClosedLap(lap_number={!r}, excluded_reason={!r}, lap_time_ms={!r})".format(
            self.lap_number, self.excluded_reason, self.lap_time_ms)


class LapUpdate(object):
    """What happened on one sample: a lap closed, the session
    restarted, both, or neither."""

    def __init__(self, closed_lap=None, restarted=False):
        self.closed_lap = closed_lap
        self.restarted = restarted


class LapTracker(object):
    """Feed it one sample per frame with update().

        laps = LapTracker()
        update = laps.update(completed_laps=11, in_pit_lane=False,
                             lap_progress=0.42, lap_time_ms=58400)
        laps.lap_progress          # 0.42
        update.closed_lap          # a ClosedLap when a lap just ended

    `lap_progress` (0..1 around the lap) and `lap_time_ms` (current lap
    time) are optional; without them there's no progress and no
    average lap time.
    """

    def __init__(self, average_window=DEFAULT_AVERAGE_WINDOW):
        self._average_window = average_window
        self.reset()

    def reset(self):
        """Forget everything, e.g. when a new session starts."""
        self._valid_lap_times = deque(maxlen=self._average_window)
        self.completed_laps = None
        self.lap_progress = None
        self.last_lap = None
        self.current_excluded_reason = None
        self._lap_time_ms = None
        self._awaiting_line = False

    def update(self, completed_laps, in_pit_lane, lap_progress=None, lap_time_ms=None):
        restarted = False
        if self.completed_laps is not None and completed_laps < self.completed_laps:
            # Session restarted (or a new session began): old laps no
            # longer describe this run.
            self.reset()
            restarted = True

        closed_lap = None
        if self.completed_laps is None:
            # On lap 1 we're watching from the start, but it's still
            # excluded as the first lap; later laps were joined mid-way.
            self._start_lap(completed_laps, EXCLUDED_PARTIAL if completed_laps > 0 else None)
            self._note_pit_lane(in_pit_lane)
        else:
            self._note_pit_lane(in_pit_lane)
            if completed_laps > self.completed_laps:
                closed_lap = self._close_lap(completed_laps)

        self._note_progress(lap_progress, lap_time_ms)
        return LapUpdate(closed_lap, restarted)

    @property
    def average_lap_time_ms(self):
        """Mean time of the last `average_window` valid laps."""
        return average(self._valid_lap_times)

    def _start_lap(self, completed_laps, excluded_reason=None):
        self.completed_laps = completed_laps
        if excluded_reason is None and completed_laps == 0:
            excluded_reason = EXCLUDED_FIRST_LAP
        self.current_excluded_reason = excluded_reason
        self.lap_progress = 0.0 if excluded_reason != EXCLUDED_PARTIAL else None
        # Right after the line (and on the grid, which sits just
        # behind it) AC's track position can still read ~0.99. Hold
        # progress at 0 until it wraps, instead of jumping to "lap
        # nearly done". A lap joined mid-way has no line to wait for.
        self._awaiting_line = excluded_reason != EXCLUDED_PARTIAL

    def _note_pit_lane(self, in_pit_lane):
        # "partial" or "first" already excludes the lap, keep it.
        if in_pit_lane and self.current_excluded_reason is None:
            self.current_excluded_reason = EXCLUDED_PIT

    def _note_progress(self, lap_progress, lap_time_ms):
        self._lap_time_ms = lap_time_ms
        if lap_progress is None:
            return
        if self._awaiting_line:
            if lap_progress > 0.5:
                lap_progress = 0.0
            else:
                self._awaiting_line = False
        self.lap_progress = lap_progress

    def _close_lap(self, completed_laps):
        # If the counter skipped (e.g. a lap completed while we
        # weren't sampling), the lap's data spans more than one lap.
        reason = self.current_excluded_reason
        if completed_laps - self.completed_laps > 1 and reason is None:
            reason = EXCLUDED_PARTIAL

        # The previous sample's time: on the closing sample AC may
        # already have reset the clock for the new lap.
        lap = ClosedLap(completed_laps, reason, self._lap_time_ms)
        if lap.is_valid and lap.lap_time_ms:
            self._valid_lap_times.append(lap.lap_time_ms)
        self.last_lap = lap

        self._start_lap(completed_laps)
        return lap
