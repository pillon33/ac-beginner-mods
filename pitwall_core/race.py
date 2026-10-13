"""
race.py — where the chequered flag is: session info and laps to go.
"""

import math

# AC_SESSION_TYPE values (see telemetry/shared_memory.py).
SESSION_PRACTICE = 0
SESSION_QUALIFY = 1
SESSION_RACE = 2
# Sessions that end on a flag. Hotlap, time attack, drift and drag
# don't, so their clock (if any) means nothing here.
FLAGGED_SESSIONS = (SESSION_PRACTICE, SESSION_QUALIFY, SESSION_RACE)


class SessionInfo(object):
    """What the session says about where the flag is."""

    def __init__(self, session_type, total_laps=0, time_left_ms=0.0,
                 is_timed_race=False, has_extra_lap=False):
        self.session_type = session_type
        self.total_laps = total_laps
        self.time_left_ms = time_left_ms
        self.is_timed_race = is_timed_race
        self.has_extra_lap = has_extra_lap


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
