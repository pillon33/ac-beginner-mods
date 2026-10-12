"""
fuel_logic.py — the fuel bookkeeping behind fuel_hud, with no `ac`,
`acsys` or shared-memory calls in it.

Keeping this file free of game calls means the exact code that runs
inside AC can be unit-tested with pytest on a normal Python install
(see tests/test_fuel_logic.py). fuel_hud.py is the thin edge that
reads the game and feeds samples in here.

PYTHON 3.3 COMPATIBLE: this file is imported by AC's embedded Python
3.3 interpreter. No f-strings, no dataclasses, no `statistics`
module. tests/test_py33_compat.py guards against the common slips.

HOW A LAP IS MEASURED
----------------------
AC doesn't report fuel used per lap, only how much fuel is in the
tank right now. So we remember the fuel level when a lap starts and
subtract the level when it ends (AC's completed-lap counter goes up).

Not every lap is representative, so each closed lap gets an
`excluded_reason`. Excluded laps still show up as "last lap", but
don't count towards the average:

  partial   we started watching mid-lap (app enabled on track)
  first     lap 1: standing start or out-lap from the grid
  pit       the car was in the pit lane at some point
  refuel    the fuel level went up during the lap
"""

from collections import deque

# A rise smaller than this is treated as float noise, not a refuel.
REFUEL_THRESHOLD_LITRES = 0.1

DEFAULT_AVERAGE_WINDOW = 5

EXCLUDED_PARTIAL = "partial"
EXCLUDED_FIRST_LAP = "first"
EXCLUDED_PIT = "pit"
EXCLUDED_REFUEL = "refuel"


class LapRecord(object):
    """One completed lap. `excluded_reason` is None for a lap that
    counts towards the average."""

    def __init__(self, lap_number, fuel_used, excluded_reason=None):
        self.lap_number = lap_number
        self.fuel_used = fuel_used
        self.excluded_reason = excluded_reason

    @property
    def is_valid(self):
        return self.excluded_reason is None

    def __repr__(self):
        return "LapRecord(lap_number={!r}, fuel_used={!r}, excluded_reason={!r})".format(
            self.lap_number, self.fuel_used, self.excluded_reason)


class FuelTracker(object):
    """Feed it one sample per frame with update(); read the current
    numbers from the properties.

        tracker = FuelTracker()
        tracker.update(fuel=51.8, completed_laps=11, in_pit_lane=False)
        tracker.current_lap_used   # litres used since the lap started
    """

    def __init__(self, average_window=DEFAULT_AVERAGE_WINDOW):
        self._average_window = average_window
        self.reset()

    def reset(self):
        """Forget everything, e.g. when a new session starts."""
        self._valid_usages = deque(maxlen=self._average_window)
        self.fuel = None
        self.last_lap = None
        self._completed_laps = None
        self._lap_start_fuel = None
        self._lap_excluded_reason = None

    def update(self, fuel, completed_laps, in_pit_lane):
        """Process one sample. Returns the LapRecord of a lap that
        closed on this sample, or None."""
        if self._completed_laps is None:
            # On lap 1 we're watching from the start, but it's still
            # excluded as the first lap; later laps were joined mid-way.
            self._start_lap(fuel, completed_laps,
                            EXCLUDED_PARTIAL if completed_laps > 0 else None)
            self._note_pit_lane(in_pit_lane)
            return None

        if completed_laps < self._completed_laps:
            # Session restarted (or a new session began): old laps no
            # longer describe this run.
            self.reset()
            return self.update(fuel, completed_laps, in_pit_lane)

        if fuel > self.fuel + REFUEL_THRESHOLD_LITRES:
            # Measure the rest of the lap from the new level, but the
            # lap as a whole no longer says anything about consumption.
            self._lap_start_fuel = fuel
            self._lap_excluded_reason = EXCLUDED_REFUEL

        self._note_pit_lane(in_pit_lane)

        closed_lap = None
        if completed_laps > self._completed_laps:
            closed_lap = self._close_lap(fuel, completed_laps)

        self.fuel = fuel
        return closed_lap

    @property
    def current_lap_used(self):
        if self._lap_start_fuel is None:
            return None
        return max(0.0, self._lap_start_fuel - self.fuel)

    @property
    def last_lap_used(self):
        if self.last_lap is None:
            return None
        return self.last_lap.fuel_used

    @property
    def average_used(self):
        """Mean of the last `average_window` valid laps, or None
        before the first valid lap."""
        return average(self._valid_usages)

    @property
    def average_lap_count(self):
        return len(self._valid_usages)

    def _start_lap(self, fuel, completed_laps, excluded_reason=None):
        self.fuel = fuel
        self._completed_laps = completed_laps
        self._lap_start_fuel = fuel
        if excluded_reason is None and completed_laps == 0:
            excluded_reason = EXCLUDED_FIRST_LAP
        self._lap_excluded_reason = excluded_reason

    def _note_pit_lane(self, in_pit_lane):
        # A refuel or "partial" reason is more specific, keep it.
        if in_pit_lane and self._lap_excluded_reason is None:
            self._lap_excluded_reason = EXCLUDED_PIT

    def _close_lap(self, fuel, completed_laps):
        # If the counter skipped (e.g. a lap completed while we
        # weren't sampling), we can't tell which lap used the fuel.
        reason = self._lap_excluded_reason
        if completed_laps - self._completed_laps > 1 and reason is None:
            reason = EXCLUDED_PARTIAL

        lap = LapRecord(
            lap_number=completed_laps,
            fuel_used=max(0.0, self._lap_start_fuel - fuel),
            excluded_reason=reason,
        )
        if lap.is_valid:
            self._valid_usages.append(lap.fuel_used)
        self.last_lap = lap

        self._start_lap(fuel, completed_laps)
        return lap


def average(values):
    values = list(values)
    if not values:
        return None
    return sum(values) / len(values)


def format_litres(value):
    """'51.80 L', or '--' when there's nothing to show yet."""
    if value is None:
        return "--"
    return "{:.2f} L".format(value)


def format_last_lap(lap):
    """'4.08 L', with the reason appended when the lap is excluded
    from the average, e.g. '4.31 L (pit)'."""
    if lap is None:
        return "--"
    text = format_litres(lap.fuel_used)
    if not lap.is_valid:
        text += " ({})".format(lap.excluded_reason)
    return text


def format_average(value, lap_count):
    """'4.11 L (5 laps)' so you can see how much data is behind it."""
    if value is None:
        return "--"
    return "{} ({} laps)".format(format_litres(value), lap_count)
