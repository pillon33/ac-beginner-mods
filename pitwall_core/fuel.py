"""
fuel.py — fuel bookkeeping and strategy maths.

HOW A LAP'S FUEL IS MEASURED
-----------------------------
AC doesn't report fuel used per lap, only how much is in the tank. So
FuelTracker remembers the level when a lap starts and subtracts the
level when LapTracker says the lap ended. A lap that LapTracker
excludes (partial, first, pit) doesn't count towards the average,
and neither does a lap where the fuel level went up ("refuel").

THE REFERENCE LAP
------------------
"Target" is the fuel per lap you can afford and still reach the flag:
fuel at the start of this lap / laps to go from the start of this
lap. To judge a lap in progress, that target is spread over the lap
using the fuel profile of the last valid lap (how much of its fuel had
been used at each point). Fuel isn't burned evenly: a long straight
uses more than a hairpin, so an even split would flag every straight
as overspending.
"""

from collections import deque

from pitwall_core.display import STATUS_BAD, STATUS_GOOD, STATUS_WARN
from pitwall_core.laps import DEFAULT_AVERAGE_WINDOW, average

# A rise smaller than this is treated as float noise, not a refuel.
REFUEL_THRESHOLD_LITRES = 0.1

EXCLUDED_REFUEL = "refuel"

# The reference profile is stored as this many slices of the lap.
PROFILE_BUCKETS = 50

# "To the flag" turns amber when the spare fuel is under one lap.
SURPLUS_WARN_LAPS = 1.0
# "This lap" turns red when it's over budget by more than this share
# of a full lap's target (amber between budget and this).
LAP_OVER_BUDGET_WARN_FRACTION = 0.02


class FuelLap(object):
    """Fuel used on one completed lap. `excluded_reason` is None for a
    lap that counts towards the average."""

    def __init__(self, lap_number, fuel_used, excluded_reason=None):
        self.lap_number = lap_number
        self.fuel_used = fuel_used
        self.excluded_reason = excluded_reason

    @property
    def is_valid(self):
        return self.excluded_reason is None

    def __repr__(self):
        return "FuelLap(lap_number={!r}, fuel_used={!r}, excluded_reason={!r})".format(
            self.lap_number, self.fuel_used, self.excluded_reason)


class FuelTracker(object):
    """Feed it the fuel level once per frame, after the LapTracker has
    seen the same frame:

        lap_update = laps.update(...)
        fuel.update(fuel_level, lap_update, laps.lap_progress)
    """

    def __init__(self, average_window=DEFAULT_AVERAGE_WINDOW):
        self._average_window = average_window
        self.reset()

    def reset(self):
        """Forget everything, e.g. when a new session starts."""
        self._valid_usages = deque(maxlen=self._average_window)
        self.fuel = None
        self.last_lap = None
        self.lap_start_fuel = None
        self.reference_profile = None
        self._refuelled = False
        self._profile_samples = [None] * PROFILE_BUCKETS

    def update(self, fuel, lap_update, lap_progress):
        """Process one sample. Returns the FuelLap of a lap that closed
        on this sample, or None."""
        if lap_update.restarted:
            self.reset()

        closed = None
        if self.lap_start_fuel is None:
            self._start_lap(fuel)
        else:
            if fuel > self.fuel + REFUEL_THRESHOLD_LITRES:
                # Measure the rest of the lap from the new level, but the
                # lap as a whole no longer says anything about consumption.
                self.lap_start_fuel = fuel
                self._refuelled = True
            if lap_update.closed_lap is not None:
                closed = self._close_lap(fuel, lap_update.closed_lap)

        self.fuel = fuel
        self._note_progress(lap_progress)
        return closed

    @property
    def current_lap_used(self):
        if self.lap_start_fuel is None:
            return None
        return max(0.0, self.lap_start_fuel - self.fuel)

    @property
    def average_used(self):
        """Mean fuel of the last `average_window` valid laps, or None
        before the first valid lap."""
        return average(self._valid_usages)

    @property
    def average_lap_count(self):
        return len(self._valid_usages)

    def _start_lap(self, fuel):
        self.fuel = fuel
        self.lap_start_fuel = fuel
        self._refuelled = False
        self._profile_samples = [None] * PROFILE_BUCKETS

    def _note_progress(self, lap_progress):
        if lap_progress is None:
            return
        bucket = min(PROFILE_BUCKETS - 1, int(lap_progress * PROFILE_BUCKETS))
        self._profile_samples[bucket] = self.current_lap_used

    def _close_lap(self, fuel, closed_lap):
        # Refuel is the more specific reason: it usually comes with a
        # pit visit, but it's why the fuel number is meaningless.
        reason = EXCLUDED_REFUEL if self._refuelled else closed_lap.excluded_reason
        lap = FuelLap(closed_lap.lap_number, max(0.0, self.lap_start_fuel - fuel), reason)
        if lap.is_valid:
            self._valid_usages.append(lap.fuel_used)
            profile = build_profile(self._profile_samples, lap.fuel_used)
            if profile is not None:
                self.reference_profile = profile
        self.last_lap = lap
        self._start_lap(fuel)
        return lap


# --- Reference profile -------------------------------------------------

def build_profile(bucket_samples, lap_fuel_used):
    """Turn per-bucket "fuel used so far" samples into the share of
    the lap's fuel used by the end of each bucket.

    Returns len(bucket_samples) + 1 points for lap progress 0, 1/N, ... 1,
    always starting at 0.0, ending at 1.0 and never decreasing. Returns
    None when too much of the lap went unsampled to trust it.
    """
    if not lap_fuel_used or lap_fuel_used <= 0:
        return None
    seen = [sample for sample in bucket_samples if sample is not None]
    if len(seen) < len(bucket_samples) // 2:
        return None

    profile = [0.0]
    running = 0.0
    for sample in bucket_samples:
        if sample is not None:
            running = max(running, min(1.0, sample / lap_fuel_used))
        profile.append(running)
    profile[-1] = 1.0
    return profile


def profile_share(profile, lap_progress):
    """Share of a lap's fuel normally used by `lap_progress`. Without a
    profile, assume fuel is burned evenly around the lap."""
    lap_progress = min(1.0, max(0.0, lap_progress))
    if profile is None:
        return lap_progress
    position = lap_progress * (len(profile) - 1)
    index = min(len(profile) - 2, int(position))
    fraction = position - index
    return profile[index] + (profile[index + 1] - profile[index]) * fraction


# --- Strategy maths ----------------------------------------------------

def laps_of_fuel(fuel, per_lap):
    """How many laps the tank lasts at `per_lap` litres a lap."""
    if fuel is None or not per_lap or per_lap <= 0:
        return None
    return fuel / per_lap


def surplus_to_flag(fuel, laps_to_go, per_lap):
    """Litres left over at the flag at the current average. Negative
    means you run dry before the flag."""
    if fuel is None or laps_to_go is None or not per_lap:
        return None
    return fuel - laps_to_go * per_lap


def target_per_lap(lap_start_fuel, laps_to_go, lap_progress):
    """Litres per lap you can afford from the start of this lap to the
    flag. Measured from the start of the lap so it holds still while
    you drive it."""
    if lap_start_fuel is None or laps_to_go is None or lap_progress is None:
        return None
    laps_from_lap_start = laps_to_go + lap_progress
    if laps_from_lap_start <= 0:
        return None
    return lap_start_fuel / laps_from_lap_start


def lap_budget_delta(current_lap_used, target, lap_progress, profile):
    """Fuel used this lap minus what the target allows by this point.
    Negative means under budget."""
    if current_lap_used is None or target is None or lap_progress is None:
        return None
    return current_lap_used - target * profile_share(profile, lap_progress)


def surplus_status(surplus, per_lap):
    if surplus is None or not per_lap:
        return None
    if surplus < 0:
        return STATUS_BAD
    if surplus / per_lap < SURPLUS_WARN_LAPS:
        return STATUS_WARN
    return STATUS_GOOD


def lap_budget_status(delta, target):
    if delta is None or not target:
        return None
    if delta <= 0:
        return STATUS_GOOD
    if delta <= target * LAP_OVER_BUDGET_WARN_FRACTION:
        return STATUS_WARN
    return STATUS_BAD
