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

WHAT COUNTS AS CROSSING THE LINE
---------------------------------
Normally AC's completed-lap counter goes up as the car crosses the
line and its lap clock restarts at 0. From a hotlap-style start (car
placed before the line, clock already running) neither can be taken
for granted: the clock may keep counting through the first crossing
and the counter may not move until a later one. So a crossing is
detected from either signal:

  * the counter going up, or
  * the track position wrapping from ~1 back to ~0.

Both usually fire for the same crossing (a few frames apart), and the
second is then ignored. The lap that ends at the first crossing is
the out lap ("first"), and the lap after it starts clean even when the
counter still reads 0.

LAP CLOCK
----------
`lap_time_ms` is the time since the last crossing. If the game's clock
restarted at the crossing it is used as is; if it kept counting, the
clock reading at the crossing (interpolated between frames by track
position) is subtracted from then on. The offset is dropped again
whenever the game's clock visibly restarts.
"""

from collections import deque

DEFAULT_AVERAGE_WINDOW = 5

# Position wrapping from above WRAP_FROM to below WRAP_TO is the line.
WRAP_FROM = 0.9
WRAP_TO = 0.1
# A drop of the game's lap clock bigger than this is a restart of it.
CLOCK_RESET_MS = 1000

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
        self._raw_position = None
        self._raw_clock = None
        self._clock_offset = 0
        self._swallow_wrap = False      # counter already credited this crossing
        self._swallow_counter = False   # position wrap already credited it

    @property
    def lap_time_ms(self):
        """Time since the last line crossing (None without a clock)."""
        return self._lap_time_ms

    def update(self, completed_laps, in_pit_lane, lap_progress=None, lap_time_ms=None):
        restarted = False
        if self.completed_laps is not None and completed_laps < self.completed_laps:
            # Session restarted (or a new session began): old laps no
            # longer describe this run.
            self.reset()
            restarted = True

        previous_position = self._raw_position
        previous_clock = self._raw_clock
        wrapped = (previous_position is not None and lap_progress is not None
                   and previous_position > WRAP_FROM and lap_progress < WRAP_TO)
        clock_reset = (lap_time_ms is not None and previous_clock is not None
                       and lap_time_ms < previous_clock - CLOCK_RESET_MS)
        closed_lap = None
        crossed = False

        if self.completed_laps is None:
            # On lap 1 we're watching from the start, but it's still
            # excluded as the first lap; later laps were joined mid-way.
            self._start_lap(completed_laps, EXCLUDED_PARTIAL if completed_laps > 0 else None)
            self._note_pit_lane(in_pit_lane)
        else:
            self._note_pit_lane(in_pit_lane)
            counter_up = completed_laps > self.completed_laps
            if counter_up and self._swallow_counter:
                # Same crossing as the position wrap that already closed the lap.
                self.completed_laps = completed_laps
                self._swallow_counter = False
            elif counter_up:
                crossed = True
                self._swallow_counter = False
                # Position usually wraps a little later; that's this crossing.
                self._swallow_wrap = (not wrapped and lap_progress is not None
                                      and lap_progress > 0.5)
            elif wrapped and self._swallow_wrap:
                self._swallow_wrap = False
            elif wrapped:
                crossed = True
                self._swallow_counter = True

            if crossed:
                closed_time = self._closing_time(
                    previous_position, previous_clock, lap_progress, lap_time_ms, clock_reset)
                closed_lap = self._close_lap(
                    completed_laps if counter_up else self.completed_laps, closed_time)

        if lap_progress is not None and 0.1 <= lap_progress <= 0.9:
            # Well away from the line: any crossing has fully happened.
            self._swallow_wrap = False
            self._swallow_counter = False

        self._update_clock(lap_time_ms, previous_clock, previous_position, lap_progress,
                           crossed, clock_reset)
        self._raw_position = lap_progress
        if lap_time_ms is not None:
            self._raw_clock = lap_time_ms
        self._note_progress(lap_progress)
        return LapUpdate(closed_lap, restarted)

    def _crossing_clock(self, previous_position, previous_clock, position, clock):
        """The game's clock at the moment of the crossing, interpolated
        between the frames either side by track position."""
        if previous_clock is None:
            return clock
        if previous_position is not None and position is not None \
                and previous_position > WRAP_FROM and position < WRAP_TO:
            distance = (1.0 - previous_position) + position
            if distance > 0:
                fraction = (1.0 - previous_position) / distance
                return previous_clock + (clock - previous_clock) * fraction
        return clock

    def _closing_time(self, previous_position, previous_clock, position, clock, clock_reset):
        # Clock restarted: the previous sample is the last reading of
        # the lap. Clock kept counting: the reading at the line.
        if clock is None or clock_reset or previous_clock is None:
            return self._lap_time_ms
        crossing = self._crossing_clock(previous_position, previous_clock, position, clock)
        return crossing - self._clock_offset

    def _update_clock(self, clock, previous_clock, previous_position, position, crossed,
                      clock_reset):
        if clock is None:
            return
        if clock_reset:
            self._clock_offset = 0
        elif crossed and previous_clock is not None:
            self._clock_offset = self._crossing_clock(
                previous_position, previous_clock, position, clock)
        self._lap_time_ms = clock - self._clock_offset

    @property
    def average_lap_time_ms(self):
        """Mean time of the last `average_window` valid laps."""
        return average(self._valid_lap_times)

    def _start_lap(self, completed_laps, excluded_reason=None, after_line=False):
        self.completed_laps = completed_laps
        if excluded_reason is None and completed_laps == 0 and not after_line:
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

    def _note_progress(self, lap_progress):
        if lap_progress is None:
            return
        if self._awaiting_line:
            if lap_progress > 0.5:
                lap_progress = 0.0
            else:
                self._awaiting_line = False
        self.lap_progress = lap_progress

    def _close_lap(self, completed_laps, lap_time_ms):
        # If the counter skipped (e.g. a lap completed while we
        # weren't sampling), the lap's data spans more than one lap.
        reason = self.current_excluded_reason
        if completed_laps - self.completed_laps > 1 and reason is None:
            reason = EXCLUDED_PARTIAL

        lap = ClosedLap(completed_laps, reason, lap_time_ms)
        if lap.is_valid and lap.lap_time_ms:
            self._valid_lap_times.append(lap.lap_time_ms)
        self.last_lap = lap

        self._start_lap(completed_laps, after_line=True)
        return lap
