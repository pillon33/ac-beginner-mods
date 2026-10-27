"""
sectors.py — best sector times this session, the theoretical best lap
built from them, and a live delta against that lap.

Data: AC's shared memory gives the index of the sector the car is in
(`currentSectorIndex`) and the time of the sector it last completed
(`lastSectorTime`, ms, the sector's own time, not a running split).
When the index changes, the sector we were in has just finished and
`last_sector_ms` is its time. The `ac` API gives the lap time so far
and the normalized track position (0..1 round the lap).

A completed sector only counts as a best-sector candidate when we
trust the number:

  * we saw it from its start (not joined mid-sector),
  * the car was not in the pit lane at any point during it,
  * it was not the standing start from the grid (sector 0 of lap 0),
  * the index moved to the expected next sector (no skipped sectors),
  * the car's position only moved forward through it,
  * we recorded a usable trace of it (below).

TRACE AND REFERENCE LAP
------------------------
While a sector is driven, a trace of (position, time since the sector
started) samples is kept, one every SAMPLE_STEP of the track and at
most MAX_SAMPLES per sector. When a sector sets a new best its trace
replaces that sector's reference segment. The reference lap is the
best segments joined end to end, each offset by the best times of the
sectors before it, so it ends exactly at the theoretical best lap.

The live delta is the lap time so far minus the reference time at the
current position (linear interpolation): negative when ahead of the
theoretical pace, positive when behind. It is recomputed on every
update and is None when there is no full reference yet, after the car
has been in the pit lane this lap, or when the position goes
backwards or jumps (until the next start/finish crossing).
"""

from bisect import bisect_left

SAMPLE_STEP = 0.005     # fraction of the lap between trace samples
MAX_SAMPLES = 400       # per sector: bounds memory
MAX_FORWARD_JUMP = 0.1  # more than this in one frame is a teleport
BACKWARD_TOLERANCE = 0.002
WRAP_FROM = 0.9         # position falling from above this to below WRAP_TO
WRAP_TO = 0.1           # is the start/finish line, not going backwards


def interpolate(points, x):
    """Linear interpolation over [(x, y), ...] sorted by x. Clamps to
    the ends; None when there are no points."""
    if not points:
        return None
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    index = bisect_left(points, (x,))
    x0, y0 = points[index - 1]
    x1, y1 = points[index]
    if x1 == x0:
        return y1
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def build_reference(traces, best_ms, sector_count):
    """Join the best segment of every sector into one lap of
    (position, time) points, or None when a sector has no segment.
    Positions and times never go backwards."""
    if not sector_count or any(index not in traces for index in range(sector_count)):
        return None
    points = []
    offset = 0
    for index in range(sector_count):
        for position, elapsed in traces[index]:
            if points:
                position = max(position, points[-1][0])
                time = max(elapsed + offset, points[-1][1])
            else:
                time = elapsed + offset
            points.append((position, time))
        offset += best_ms[index]
    return points


class SectorTracker(object):

    def __init__(self):
        self.reset()

    def reset(self):
        """Forget everything, e.g. when a new session starts."""
        self.best_ms = {}            # sector index -> best time
        self.best_trace = {}         # sector index -> [(position, ms into sector)]
        self.sector_count = None
        self.delta_ms = None
        self._reference = None
        self._sector = None
        self._watched = False        # saw the current sector from its start
        self._sector_tainted = False
        self._on_grid = False
        self._lap_splits = []
        self._lap_tainted = False
        self._trace = []
        self._trace_base = None      # lap time at the sector's start
        self._last_pos = None
        self._delta_ok = True

    def update(self, current_sector, last_sector_ms, in_pit_lane, completed_laps,
               sector_count=None, restarted=False, lap_progress=None, lap_time_ms=None):
        if restarted:
            self.reset()
        if sector_count:
            self.sector_count = sector_count
        self.delta_ms = None
        if current_sector is None:
            return

        if in_pit_lane:
            self._sector_tainted = True
            self._delta_ok = False
        if self._sector is None:
            self._begin(current_sector, completed_laps, watched=False)
        elif current_sector != self._sector:
            self._complete(current_sector, last_sector_ms)
            self._begin(current_sector, completed_laps, watched=True)
        if in_pit_lane:
            self._sector_tainted = True
            self._delta_ok = False

        self._track(lap_progress, lap_time_ms)

    @property
    def theoretical_best_ms(self):
        """Sum of the best time of every sector, or None until each
        sector has a counted time."""
        if not self.sector_count:
            return None
        if any(index not in self.best_ms for index in range(self.sector_count)):
            return None
        return sum(self.best_ms[index] for index in range(self.sector_count))

    def _begin(self, sector, completed_laps, watched):
        self._sector = sector
        self._watched = watched
        self._sector_tainted = False
        self._on_grid = sector == 0 and completed_laps == 0
        self._trace = []
        if sector == 0:
            self._trace_base = 0
            self._delta_ok = True
        elif not self._lap_tainted and len(self._lap_splits) == sector:
            self._trace_base = sum(self._lap_splits)
        else:
            self._trace_base = None   # taken from the first sample

    def _is_next(self, old, new):
        if self.sector_count:
            return new == (old + 1) % self.sector_count
        return new == old + 1 or (new == 0 and old > 0)

    def _implausible(self, position):
        """Position that can't belong to this sector: the last frames
        before the index and the position wrap are out of step."""
        if self._sector == 0 and position > 0.5:
            return True
        return bool(self.sector_count) and self._sector == self.sector_count - 1 and position < 0.5

    def _track(self, position, lap_time_ms):
        """Per-frame work: advance the trace, compute the live delta."""
        if position is None or lap_time_ms is None:
            return
        previous = self._last_pos
        self._last_pos = position
        if previous is not None:
            if previous > WRAP_FROM and position < WRAP_TO:
                self._delta_ok = True        # crossed the line
                return self._set_delta(position, lap_time_ms)
            if position < previous - BACKWARD_TOLERANCE or position - previous > MAX_FORWARD_JUMP:
                self._delta_ok = False
                self._sector_tainted = True
        if self._implausible(position):
            return
        self._record(position, lap_time_ms)
        self._set_delta(position, lap_time_ms)

    def _record(self, position, lap_time_ms):
        if not self._watched or self._sector_tainted:
            return
        if self._trace_base is None:
            self._trace_base = lap_time_ms
        elapsed = lap_time_ms - self._trace_base
        if elapsed < 0 or len(self._trace) >= MAX_SAMPLES:
            self._sector_tainted = True
            return
        if not self._trace or position - self._trace[-1][0] >= SAMPLE_STEP:
            self._trace.append((position, elapsed))

    def _set_delta(self, position, lap_time_ms):
        if not self._delta_ok or self._reference is None or self._implausible(position):
            return
        self.delta_ms = lap_time_ms - interpolate(self._reference, position)

    def _finish_trace(self, old, sector_ms):
        """The closed sector's trace as a reference segment, or None."""
        if not self._trace:
            return None
        if old == 0 and self._trace[0][0] > 0:
            trace = [(0.0, 0)] + self._trace
        else:
            trace = list(self._trace)
        if self.sector_count and old == self.sector_count - 1:
            end = 1.0
        else:
            end = max(trace[-1][0], self._last_pos or 0.0)
        trace = [(p, t) for p, t in trace if t < sector_ms]
        if not trace:
            return None
        trace.append((end, sector_ms))
        return trace

    def _complete(self, new, sector_ms):
        old = self._sector
        counted = (self._is_next(old, new) and self._watched and not self._sector_tainted
                   and not self._on_grid and sector_ms is not None and sector_ms > 0)
        trace = self._finish_trace(old, sector_ms) if counted else None
        counted = trace is not None
        if counted:
            if old not in self.best_ms or sector_ms < self.best_ms[old]:
                self.best_ms[old] = sector_ms
                self.best_trace[old] = trace
                self._reference = build_reference(self.best_trace, self.best_ms,
                                                  self.sector_count)
            if not self._lap_tainted and len(self._lap_splits) == old:
                self._lap_splits.append(sector_ms)
            else:
                self._lap_tainted = True
        else:
            self._lap_tainted = True

        if new == 0:
            # Crossed the line: next lap's splits start afresh.
            self._lap_splits = []
            self._lap_tainted = False
