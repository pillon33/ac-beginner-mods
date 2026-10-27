"""
sectors.py — best mini-sector times this session, the theoretical best
lap built from them, and a live delta against that lap.

MINI-SECTORS
-------------
The lap is cut into MINI_SECTORS equal slices of normalized track
position (lap_progress boundaries, not AC's three sectors). A mini
sector's time is measured from the lap-time samples around its two
boundary crossings, interpolated between frames, so it doesn't depend
on any AC sector field. The only inputs are the pit-lane flag, the
track position and the lap time so far.

A mini-sector only counts when it was watched from its start to its
end, the car was not in the pit lane at any point during it, and the
position only moved forward through it. We also keep a trace of it,
(position, time since the slice began) samples, one every SAMPLE_STEP
of the lap.

REFERENCE LAP (frozen for a whole lap)
---------------------------------------
Counted mini-sectors of the lap in progress are held as pending. At the
start/finish crossing, if the lap was clean (no pit lane, no position
jumps or reversals) they are merged into the session bests and the
reference lap is rebuilt from the best segment of every mini-sector
joined end to end, so it ends exactly at the theoretical best. A lap
that is not clean contributes nothing. (From a grid or hotlap start the
first lap, which ends at the first crossing, is such an out lap: its
position is not trusted and none of its slices count.) The reference only ever changes
at the line, so the delta and the theoretical best shown during a lap
all refer to the same reference.

MINI-SECTOR BOXES
------------------
`slice_statuses` gives one status per mini-sector for the lap being
driven (display.slice_status of each slice's time against the frozen
reference's time for that slice; None for slices not driven yet, not
counted, or without a reference). When a lap finishes its statuses
stay up until the first slice of the next lap has been completed.

LIVE DELTA
-----------
The lap time so far minus the reference time at the current position
(linear interpolation), recomputed on every update: negative when
ahead of the theoretical pace, positive when behind. It is None when
there is no full reference yet, once the car has been in the pit lane
this lap, or when the position goes backwards or jumps; it comes back
at the next start/finish crossing.
"""

from bisect import bisect_left

from pitwall_core.display import slice_status

MINI_SECTORS = 20       # equal slices of the lap by normalized position
SAMPLE_STEP = 0.005     # fraction of the lap between trace samples
MAX_SAMPLES = 400       # per mini-sector: bounds memory
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


def build_reference(traces, best_ms, count):
    """Join the best segment of every mini-sector into one lap of
    (position, time) points, or None when a slice has no segment.
    Positions and times never go backwards."""
    if not count or any(index not in traces for index in range(count)):
        return None
    points = []
    offset = 0
    for index in range(count):
        for position, elapsed in traces[index]:
            if points:
                position = max(position, points[-1][0])
                time = max(elapsed + offset, points[-1][1])
            else:
                time = elapsed + offset
            points.append((position, time))
        offset += best_ms[index]
    return points


class MiniSectorTracker(object):

    def __init__(self, count=MINI_SECTORS):
        self.count = count
        self.reset()

    def reset(self):
        """Forget everything, e.g. when a new session starts."""
        self.best_ms = {}            # mini-sector -> best time this session
        self.best_trace = {}         # mini-sector -> [(position, ms into slice)]
        self.delta_ms = None
        self._reference = None       # frozen until the next start/finish crossing
        self._theoretical_ms = None
        self._pending = {}           # this lap's counted mini-sectors
        self._ref_ms = {}            # slice bests as of the last line crossing
        self._lap_boxes = [None] * self.count
        self._last_boxes = [None] * self.count
        self._lap_ok = True          # clean so far: may feed the reference
        self._delta_ok = True
        self._prev = None            # (position, lap time) of the last frame
        self._rate = None            # ms per unit of position, last frame
        self._mini = None
        self._start = None           # (position, lap time) the slice began at
        self._trace = []
        self._watched = False
        self._tainted = False

    def update(self, in_pit_lane, lap_progress, lap_time_ms, restarted=False,
               line_crossed=False):
        if restarted:
            self.reset()
        self.delta_ms = None
        if lap_progress is None or lap_time_ms is None:
            return

        if in_pit_lane:
            self._pit()
        current = (lap_progress, lap_time_ms)
        if self._prev is None:
            self._enter(lap_progress)
            self._prev = current
        else:
            self._advance(self._prev, current)
        if line_crossed and lap_progress < WRAP_TO and not (self._mini == 0 and self._watched):
            # The lap tracker saw the line but the position never wrapped
            # in our eyes (it is held at 0 until the line on a grid or
            # hotlap start): the lap ahead is watched from its very
            # start, on a lap clock that is 0 at the line.
            self._end_lap()
            self._open(0, 0.0, 0.0, watched=True)
        if in_pit_lane:
            self._pit()      # also spoils a slice (and lap) just entered
        self._set_delta(lap_progress, lap_time_ms)

    @property
    def theoretical_best_ms(self):
        """Sum of the best time of every mini-sector in the reference
        lap, or None until there is one. Changes only at the line."""
        return self._theoretical_ms

    @property
    def slice_statuses(self):
        """One status (or None) per mini-sector: the current lap's, or
        the finished lap's until the new lap completes a slice."""
        if any(status is not None for status in self._lap_boxes):
            return list(self._lap_boxes)
        return list(self._last_boxes)

    # -- per frame -------------------------------------------------

    def _pit(self):
        self._lap_ok = False
        self._delta_ok = False
        self._tainted = True

    def _enter(self, position):
        """First sample, or after a jump: not watched from a boundary,
        so this slice can't count."""
        self._mini = min(int(position * self.count), self.count - 1)
        self._start = None
        self._trace = []
        self._watched = False
        self._tainted = True
        self._prev = None

    def _advance(self, prev, current):
        position, lap_time = current
        prev_position = prev[0]
        if prev_position > WRAP_FROM and position < WRAP_TO:
            self._cross_line(prev, current)
        elif position < prev_position - BACKWARD_TOLERANCE or \
                position - prev_position > MAX_FORWARD_JUMP:
            self._lap_ok = False
            self._delta_ok = False
            self._enter(position)
        elif position > prev_position:
            self._segment(prev, current)
        else:
            return           # standing still (or sub-tolerance jitter)
        self._prev = current

    def _cross_line(self, prev, current):
        """Position wrapped: finish the old lap by extrapolating at the
        speed of the last frames, then start the new lap the same way
        from the line."""
        position, lap_time = current
        rate = self._rate
        if not rate or rate <= 0:
            self._lap_ok = False
            self._enter(position)
            return
        line_old = prev[1] + rate * (1.0 - prev[0])
        self._segment(prev, (1.0, line_old))
        self._end_lap()
        line_new = lap_time - rate * position
        self._open(0, 0.0, line_new, watched=True)
        self._segment((0.0, line_new), current)

    def _segment(self, prev, current):
        """Advance from prev to current within one lap: close every
        mini-sector whose end boundary lies in between."""
        (p0, t0), (p1, t1) = prev, current
        if p1 > p0:
            self._rate = (t1 - t0) / (p1 - p0)
        while self._mini < self.count:
            boundary = (self._mini + 1) / float(self.count)
            if p1 < boundary:
                break
            time = t0 + (t1 - t0) * (boundary - p0) / (p1 - p0) if p1 > p0 else t1
            self._close(boundary, time)
            if self._mini + 1 >= self.count:
                self._mini = self.count     # past the line; caller restarts
                return
            self._open(self._mini + 1, boundary, time, watched=True)
        self._sample(p1, t1)

    def _open(self, index, position, time, watched):
        self._mini = index
        self._start = (position, time)
        self._trace = [(position, 0)] if watched else []
        self._watched = watched
        self._tainted = False

    def _sample(self, position, lap_time):
        if not self._watched or self._tainted or self._start is None or self._mini >= self.count:
            return
        if len(self._trace) >= MAX_SAMPLES:
            return
        if position - self._trace[-1][0] >= SAMPLE_STEP:
            self._trace.append((position, lap_time - self._start[1]))

    def _close(self, position, time):
        if not self._watched or self._tainted or self._start is None:
            return
        elapsed = time - self._start[1]
        if elapsed <= 0:
            return
        trace = [(p, t) for p, t in self._trace if t < elapsed]
        trace.append((position, elapsed))
        self._pending[self._mini] = (elapsed, trace)
        reference = self._ref_ms.get(self._mini)
        if reference is not None:
            self._lap_boxes[self._mini] = slice_status(elapsed - reference)

    def _end_lap(self):
        """Start/finish crossing: promote a clean lap's mini-sectors
        into the bests and refresh the reference."""
        if self._lap_ok:
            for index, (ms, trace) in self._pending.items():
                if index not in self.best_ms or ms < self.best_ms[index]:
                    self.best_ms[index] = ms
                    self.best_trace[index] = trace
            self._ref_ms = dict(self.best_ms)
            self._reference = build_reference(self.best_trace, self.best_ms, self.count)
            if self._reference is not None:
                self._theoretical_ms = self._reference[-1][1]
        if any(status is not None for status in self._lap_boxes):
            self._last_boxes = self._lap_boxes
        self._lap_boxes = [None] * self.count
        self._pending = {}
        self._lap_ok = True
        self._delta_ok = True

    def _set_delta(self, position, lap_time_ms):
        if not self._delta_ok or self._reference is None:
            return
        self.delta_ms = lap_time_ms - interpolate(self._reference, position)
