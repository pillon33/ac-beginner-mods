"""
sectors.py — best sector times this session, the theoretical best
lap built from them, and a live delta to that theoretical lap.

Data: AC's shared memory gives the index of the sector the car is in
(`currentSectorIndex`) and the time of the sector it last completed
(`lastSectorTime`, ms, the sector's own time, not a running split).
When the index changes, the sector we were in has just finished and
`last_sector_ms` is its time.

A completed sector only counts as a best-sector candidate when we
trust the number:

  * we saw it from its start (not joined mid-sector),
  * the car was not in the pit lane at any point during it,
  * it was not the standing start from the grid (sector 0 of lap 0),
  * the index moved to the expected next sector (no skipped sectors).

The theoretical best lap is the sum of the best time of every sector,
so it exists only once each sector has a counted time and the number
of sectors is known (static `sectorCount`).

Live delta (`delta_ms`), updated every frame:

  * Completed sectors of this lap: their time minus the best time
    of that sector *before* this lap's run through it, so a faster
    sector shows as a negative gap instead of being compared with
    itself.
  * The sector the car is in: time spent in it so far minus the time
    the best run through it had taken at the same track position.
    Every counted sector records a trace of (lap progress, time in
    sector); the trace of each sector's best run is the reference.

The lap restarts at 0 at the line. A lap with an uncounted sector
(pit, mid-lap join, ...), or one through a sector with no best yet,
has no delta: None. Without lap progress and lap time the live part
is 0 and the delta only moves at each split.
"""

from bisect import bisect_left

# AC's lap clock and the sector index don't change on exactly the
# same frame. Until the time in a new sector reads as having just
# started, the clock is still on the old lap or sector: skip it.
CLOCK_SETTLE_MS = 2000


class SectorTracker(object):

    def __init__(self):
        self.reset()

    def reset(self):
        """Forget everything, e.g. when a new session starts."""
        self.best_ms = {}            # sector index -> best time
        self.sector_count = None
        self.delta_ms = None
        self._references = {}        # sector index -> (progresses, times) of its best run
        self._sector = None
        self._watched = False        # saw the current sector from its start
        self._sector_tainted = False
        self._on_grid = False
        self._lap_delta = None       # gap over this lap's completed sectors
        self._sector_start_ms = 0    # lap time when the current sector began
        self._start_trace()

    def update(self, current_sector, last_sector_ms, in_pit_lane, completed_laps,
               sector_count=None, restarted=False, lap_progress=None, lap_time_ms=None):
        if restarted:
            self.reset()
        if sector_count:
            self.sector_count = sector_count
        if current_sector is None:
            return

        if in_pit_lane:
            self._sector_tainted = True
        if self._sector is None:
            self._begin(current_sector, completed_laps, watched=False)
        elif current_sector != self._sector:
            self._complete(current_sector, last_sector_ms)
            self._begin(current_sector, completed_laps, watched=True)
        if in_pit_lane:
            self._sector_tainted = True

        self._sample(lap_progress, lap_time_ms)
        if self._lap_delta is None or self._sector_tainted:
            self.delta_ms = None
        else:
            self.delta_ms = self._lap_delta + self._live_ms

    @property
    def theoretical_best_ms(self):
        """Sum of the best time of every sector, or None until each
        sector has a counted time."""
        if not self.sector_count:
            return None
        if any(index not in self.best_ms for index in range(self.sector_count)):
            return None
        return sum(self.best_ms[index] for index in range(self.sector_count))

    def _start_trace(self):
        # Fresh lists: the finished ones may now be a reference.
        self._trace_progress = []
        self._trace_ms = []
        self._clock_settled = False
        self._live_ms = 0            # gap in the current sector so far

    def _begin(self, sector, completed_laps, watched):
        self._sector = sector
        self._watched = watched
        self._sector_tainted = False
        self._on_grid = sector == 0 and completed_laps == 0
        if not watched:
            self._lap_delta = None
        self._start_trace()

    def _is_next(self, old, new):
        if self.sector_count:
            return new == (old + 1) % self.sector_count
        return new == old + 1 or (new == 0 and old > 0)

    def _complete(self, new, sector_ms):
        old = self._sector
        counted = (self._is_next(old, new) and self._watched and not self._sector_tainted
                   and not self._on_grid and sector_ms is not None and sector_ms > 0)
        previous_best = self.best_ms.get(old)
        if counted and self._lap_delta is not None and previous_best is not None:
            self._lap_delta += sector_ms - previous_best
        else:
            self._lap_delta = None
        if counted and (previous_best is None or sector_ms < previous_best):
            self.best_ms[old] = sector_ms
            self._references[old] = (self._trace_progress, self._trace_ms)
        if sector_ms:
            self._sector_start_ms += sector_ms

        if new == 0:
            # Crossed the line: the next lap starts afresh.
            self._lap_delta = 0
            self._sector_start_ms = 0

    def _sample(self, progress, lap_time_ms):
        """Add this frame to the current sector's trace and update the
        live gap against the reference at the same track position."""
        if progress is None or lap_time_ms is None:
            return
        if not self._watched or self._sector_tainted:
            return
        in_sector_ms = lap_time_ms - self._sector_start_ms
        if not self._clock_settled:
            # Just after the line the track position can still read
            # ~0.99 for a frame or two.
            if not 0 <= in_sector_ms < CLOCK_SETTLE_MS or (self._sector == 0 and progress > 0.5):
                return
            self._clock_settled = True
        # Going backwards means the position wrapped past the line
        # before the sector index changed.
        if in_sector_ms < 0 or (self._trace_progress and progress < self._trace_progress[-1]):
            return
        self._trace_progress.append(progress)
        self._trace_ms.append(in_sector_ms)

        reference_ms = self._reference_ms(progress)
        if reference_ms is not None:
            self._live_ms = in_sector_ms - reference_ms

    def _reference_ms(self, progress):
        """Time the best run through the current sector had spent in it
        at `progress`, interpolated between its trace points."""
        reference = self._references.get(self._sector)
        if not reference or not reference[0]:
            return None
        progresses, times = reference
        index = bisect_left(progresses, progress)
        if index == 0:
            return times[0]
        if index == len(progresses):
            return times[-1]
        p0, p1 = progresses[index - 1], progresses[index]
        t0, t1 = times[index - 1], times[index]
        if p1 == p0:
            return t1
        return t0 + (t1 - t0) * (progress - p0) / (p1 - p0)
