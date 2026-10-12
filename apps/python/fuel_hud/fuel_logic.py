"""
fuel_logic.py — the fuel bookkeeping and race maths behind fuel_hud,
with no `ac`, `acsys` or shared-memory calls in it.

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
don't count towards the averages:

  partial   we started watching mid-lap (app enabled on track)
  first     lap 1: standing start or out-lap from the grid
  pit       the car was in the pit lane at some point
  refuel    the fuel level went up during the lap

THE REFERENCE LAP
------------------
"Target" is the fuel per lap you can afford and still reach the flag:
fuel at the start of this lap / laps to go from the start of this
lap. To judge the lap while it's in progress, that target is spread
over the lap using the fuel profile of the last valid lap (how much
of its fuel had been used at each point). Fuel isn't burned evenly:
a long straight uses more than a hairpin, so a straight-line split
would flag every straight as overspending.
"""

import math
from collections import deque

# A rise smaller than this is treated as float noise, not a refuel.
REFUEL_THRESHOLD_LITRES = 0.1

DEFAULT_AVERAGE_WINDOW = 5

# The reference profile is stored as this many slices of the lap.
PROFILE_BUCKETS = 50

# AC_SESSION_TYPE values (see telemetry/shared_memory.py).
SESSION_PRACTICE = 0
SESSION_QUALIFY = 1
SESSION_RACE = 2
# Sessions that end on a flag. Hotlap, time attack, drift and drag
# don't, so their clock (if any) means nothing for fuel.
FLAGGED_SESSIONS = (SESSION_PRACTICE, SESSION_QUALIFY, SESSION_RACE)

EXCLUDED_PARTIAL = "partial"
EXCLUDED_FIRST_LAP = "first"
EXCLUDED_PIT = "pit"
EXCLUDED_REFUEL = "refuel"

STATUS_GOOD = "good"
STATUS_WARN = "warn"
STATUS_BAD = "bad"

# "To the flag" turns amber when the spare fuel is under one lap.
SURPLUS_WARN_LAPS = 1.0
# "This lap" turns red when it's over budget by more than this share
# of a full lap's target (amber between budget and this).
LAP_OVER_BUDGET_WARN_FRACTION = 0.02


class LapRecord(object):
    """One completed lap. `excluded_reason` is None for a lap that
    counts towards the averages."""

    def __init__(self, lap_number, fuel_used, excluded_reason=None, lap_time_ms=None):
        self.lap_number = lap_number
        self.fuel_used = fuel_used
        self.excluded_reason = excluded_reason
        self.lap_time_ms = lap_time_ms

    @property
    def is_valid(self):
        return self.excluded_reason is None

    def __repr__(self):
        return ("LapRecord(lap_number={!r}, fuel_used={!r}, excluded_reason={!r}, "
                "lap_time_ms={!r})").format(
            self.lap_number, self.fuel_used, self.excluded_reason, self.lap_time_ms)


class SessionInfo(object):
    """What the session says about where the flag is. Built by the HUD
    from shared memory each frame."""

    def __init__(self, session_type, total_laps=0, time_left_ms=0.0,
                 is_timed_race=False, has_extra_lap=False):
        self.session_type = session_type
        self.total_laps = total_laps
        self.time_left_ms = time_left_ms
        self.is_timed_race = is_timed_race
        self.has_extra_lap = has_extra_lap


class FuelTracker(object):
    """Feed it one sample per frame with update(); read the current
    numbers from the properties.

        tracker = FuelTracker()
        tracker.update(fuel=51.8, completed_laps=11, in_pit_lane=False,
                       lap_progress=0.42, lap_time_ms=58400)
        tracker.current_lap_used   # litres used since the lap started

    `lap_progress` (0..1 around the lap) and `lap_time_ms` (current
    lap time) are optional; without them there's no reference
    profile and no average lap time.
    """

    def __init__(self, average_window=DEFAULT_AVERAGE_WINDOW):
        self._average_window = average_window
        self.reset()

    def reset(self):
        """Forget everything, e.g. when a new session starts."""
        self._valid_usages = deque(maxlen=self._average_window)
        self._valid_lap_times = deque(maxlen=self._average_window)
        self.fuel = None
        self.last_lap = None
        self.lap_progress = None
        self.reference_profile = None
        self._completed_laps = None
        self._lap_start_fuel = None
        self._lap_excluded_reason = None
        self._lap_time_ms = None
        self._awaiting_line = False
        self._profile_samples = [None] * PROFILE_BUCKETS

    def update(self, fuel, completed_laps, in_pit_lane, lap_progress=None, lap_time_ms=None):
        """Process one sample. Returns the LapRecord of a lap that
        closed on this sample, or None."""
        if self._completed_laps is None:
            # On lap 1 we're watching from the start, but it's still
            # excluded as the first lap; later laps were joined mid-way.
            self._start_lap(fuel, completed_laps,
                            EXCLUDED_PARTIAL if completed_laps > 0 else None)
            self._note_pit_lane(in_pit_lane)
            self._note_progress(lap_progress, lap_time_ms)
            return None

        if completed_laps < self._completed_laps:
            # Session restarted (or a new session began): old laps no
            # longer describe this run.
            self.reset()
            return self.update(fuel, completed_laps, in_pit_lane, lap_progress, lap_time_ms)

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
        self._note_progress(lap_progress, lap_time_ms)
        return closed_lap

    @property
    def current_lap_used(self):
        if self._lap_start_fuel is None:
            return None
        return max(0.0, self._lap_start_fuel - self.fuel)

    @property
    def lap_start_fuel(self):
        return self._lap_start_fuel

    @property
    def last_lap_used(self):
        if self.last_lap is None:
            return None
        return self.last_lap.fuel_used

    @property
    def average_used(self):
        """Mean fuel of the last `average_window` valid laps, or None
        before the first valid lap."""
        return average(self._valid_usages)

    @property
    def average_lap_count(self):
        return len(self._valid_usages)

    @property
    def average_lap_time_ms(self):
        return average(self._valid_lap_times)

    def _start_lap(self, fuel, completed_laps, excluded_reason=None):
        self.fuel = fuel
        self._completed_laps = completed_laps
        self._lap_start_fuel = fuel
        if excluded_reason is None and completed_laps == 0:
            excluded_reason = EXCLUDED_FIRST_LAP
        self._lap_excluded_reason = excluded_reason
        self._profile_samples = [None] * PROFILE_BUCKETS
        self.lap_progress = 0.0 if excluded_reason != EXCLUDED_PARTIAL else None
        # Right after the line (and on the grid, which sits just
        # behind it) AC's track position can still read ~0.99. Hold
        # progress at 0 until it wraps, instead of jumping to "lap
        # nearly done". A lap joined mid-way has no line to wait for.
        self._awaiting_line = excluded_reason != EXCLUDED_PARTIAL

    def _note_pit_lane(self, in_pit_lane):
        # A refuel or "partial" reason is more specific, keep it.
        if in_pit_lane and self._lap_excluded_reason is None:
            self._lap_excluded_reason = EXCLUDED_PIT

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
        bucket = min(PROFILE_BUCKETS - 1, int(lap_progress * PROFILE_BUCKETS))
        self._profile_samples[bucket] = self.current_lap_used

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
            # The previous sample's time: on the closing sample AC may
            # already have reset the clock for the new lap.
            lap_time_ms=self._lap_time_ms,
        )
        if lap.is_valid:
            self._valid_usages.append(lap.fuel_used)
            if lap.lap_time_ms:
                self._valid_lap_times.append(lap.lap_time_ms)
            profile = build_profile(self._profile_samples, lap.fuel_used)
            if profile is not None:
                self.reference_profile = profile
        self.last_lap = lap

        self._start_lap(fuel, completed_laps)
        return lap


def average(values):
    values = list(values)
    if not values:
        return None
    return sum(values) / len(values)


# --- Reference profile -------------------------------------------------

def build_profile(bucket_samples, lap_fuel_used):
    """Turn per-bucket "fuel used so far" samples into the share of
    the lap's fuel used by the end of each bucket.

    Returns PROFILE_BUCKETS + 1 points for lap progress 0, 1/N, ... 1,
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


# --- Race maths --------------------------------------------------------

def laps_of_fuel(fuel, per_lap):
    """How many laps the tank lasts at `per_lap` litres a lap."""
    if fuel is None or not per_lap or per_lap <= 0:
        return None
    return fuel / per_lap


def laps_to_go_lap_race(total_laps, completed_laps, lap_progress):
    return max(0.0, total_laps - completed_laps - lap_progress)


def laps_to_go_timed(time_left_ms, avg_lap_ms, lap_progress, has_extra_lap=False):
    """Laps left in a timed session. When the clock hits zero you
    still finish the lap you're on, so this counts every lap that
    starts before the clock runs out: ceil(time / lap + progress)
    minus the progress already made. When the clock has already run
    out it can't tell an extra lap from the final one, so it only
    counts the current lap."""
    if not avg_lap_ms or avg_lap_ms <= 0:
        return None
    time_left_ms = max(0.0, time_left_ms)
    laps = math.ceil(time_left_ms / avg_lap_ms + lap_progress) - lap_progress
    if has_extra_lap and time_left_ms > 0:
        laps += 1
    return max(0.0, laps)


def laps_to_flag(session, completed_laps, lap_progress, avg_lap_ms):
    """Laps left until the chequered flag, or None when the session
    has no flag we can predict (hotlap, or a timed session before the
    first valid lap gives us a lap time). Practice and qualifying count
    as timed sessions, so the numbers work while testing."""
    if session is None or lap_progress is None:
        return None
    if session.session_type not in FLAGGED_SESSIONS:
        return None
    is_race = session.session_type == SESSION_RACE
    if is_race and not session.is_timed_race and session.total_laps > 0:
        return laps_to_go_lap_race(session.total_laps, completed_laps, lap_progress)
    if session.time_left_ms > 0 or (is_race and session.is_timed_race):
        return laps_to_go_timed(session.time_left_ms, avg_lap_ms, lap_progress,
                                session.has_extra_lap and is_race)
    return None


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


# --- Display text ------------------------------------------------------

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


def format_laps(value):
    """'12.6' laps."""
    if value is None:
        return "--"
    return "{:.1f}".format(value)


def format_surplus(surplus, per_lap):
    """'+2.30 L (+0.6 laps)' / '-4.00 L (-1.0 laps)'. ASCII signs:
    AC's default font has no Unicode minus."""
    if surplus is None or not per_lap:
        return "--"
    return "{:+.2f} L ({:+.1f} laps)".format(surplus, surplus / per_lap)


def format_target(target):
    if target is None:
        return "--"
    return "{:.2f} L/lap".format(target)


def format_current_lap(used, delta):
    """'1.73 L (+0.04)': used so far, then how far over (+) or under
    (-) the target budget for this point of the lap."""
    text = format_litres(used)
    if used is not None and delta is not None:
        text += " ({:+.2f})".format(delta)
    return text
