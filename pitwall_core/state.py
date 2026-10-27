"""
state.py — one frame of game data, and the trackers every window
reads from.

The app reads the game once per frame into a Frame and hands it to
RaceState.update(). Every window then renders from the same
RaceState, so they can never disagree about which lap it is or which
laps count.
"""

from pitwall_core.fuel import FuelTracker
from pitwall_core.laps import LapTracker
from pitwall_core.race import laps_to_flag
from pitwall_core.sectors import MiniSectorTracker


class Frame(object):
    """Everything read from the game on one frame. Building one is the
    only place that touches `ac` or shared memory."""

    def __init__(self, fuel, completed_laps, in_pit_lane, lap_progress=None,
                 lap_time_ms=None, speed_kmh=None, gear=None, session=None):
        self.fuel = fuel
        self.completed_laps = completed_laps
        self.in_pit_lane = in_pit_lane
        self.lap_progress = lap_progress
        self.lap_time_ms = lap_time_ms
        self.speed_kmh = speed_kmh
        self.gear = gear
        self.session = session


class RaceState(object):
    """The shared trackers, updated once per frame."""

    def __init__(self):
        self.laps = LapTracker()
        self.fuel = FuelTracker()
        self.sectors = MiniSectorTracker()
        self.frame = None

    def update(self, frame):
        self.frame = frame
        lap_update = self.laps.update(frame.completed_laps, frame.in_pit_lane,
                                      frame.lap_progress, frame.lap_time_ms)
        self.fuel.update(frame.fuel, lap_update, self.laps.lap_progress)
        self.sectors.update(frame.in_pit_lane, self.laps.lap_progress, frame.lap_time_ms,
                            lap_update.restarted)

    @property
    def laps_to_flag(self):
        if self.frame is None:
            return None
        return laps_to_flag(self.frame.session, self.laps.completed_laps,
                            self.laps.lap_progress, self.laps.average_lap_time_ms)
