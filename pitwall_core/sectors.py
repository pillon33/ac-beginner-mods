"""
sectors.py — best sector times this session and the theoretical best
lap built from them.

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

The running delta (`delta_ms`) is updated at each counted split of
a lap: the lap's sector times so far minus the best times of those
same sectors. It is held across the line until the next split, so
right after a lap it shows that lap's full delta. A lap that has an
uncounted sector (pit, mid-lap join, ...) has no delta: None.
"""


class SectorTracker(object):

    def __init__(self):
        self.reset()

    def reset(self):
        """Forget everything, e.g. when a new session starts."""
        self.best_ms = {}            # sector index -> best time
        self.sector_count = None
        self.delta_ms = None
        self._sector = None
        self._watched = False        # saw the current sector from its start
        self._sector_tainted = False
        self._on_grid = False
        self._lap_splits = []
        self._lap_tainted = False

    def update(self, current_sector, last_sector_ms, in_pit_lane, completed_laps,
               sector_count=None, restarted=False):
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

    def _is_next(self, old, new):
        if self.sector_count:
            return new == (old + 1) % self.sector_count
        return new == old + 1 or (new == 0 and old > 0)

    def _complete(self, new, sector_ms):
        old = self._sector
        counted = (self._is_next(old, new) and self._watched and not self._sector_tainted
                   and not self._on_grid and sector_ms is not None and sector_ms > 0)
        if counted:
            if old not in self.best_ms or sector_ms < self.best_ms[old]:
                self.best_ms[old] = sector_ms
            if not self._lap_tainted and len(self._lap_splits) == old:
                self._lap_splits.append(sector_ms)
                self.delta_ms = sum(self._lap_splits) - sum(
                    self.best_ms[index] for index in range(len(self._lap_splits)))
            else:
                self._lap_tainted = True
                self.delta_ms = None
        else:
            self._lap_tainted = True
            self.delta_ms = None

        if new == 0:
            # Crossed the line: next lap's splits start afresh. The
            # delta stays until its first split.
            self._lap_splits = []
            self._lap_tainted = False
