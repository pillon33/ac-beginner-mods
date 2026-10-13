"""
ac_frame.py — read one Frame from the game.

Lap count, lap progress, lap time, pit lane, speed and gear come from
the `ac` API. Fuel and session length aren't in it (see the CS list in
<AC install>\\apps\\python\\system\\acsys.py), so they come from shared
memory.
"""

import ac
import acsys

from pitwall_core.race import SessionInfo
from pitwall_core.state import Frame

PLAYER_CAR = 0


def read_frame(memory):
    return Frame(
        fuel=memory.physics.get("fuel"),
        completed_laps=ac.getCarState(PLAYER_CAR, acsys.CS.LapCount),
        in_pit_lane=bool(ac.isCarInPitline(PLAYER_CAR)),
        lap_progress=ac.getCarState(PLAYER_CAR, acsys.CS.NormalizedSplinePosition),
        lap_time_ms=ac.getCarState(PLAYER_CAR, acsys.CS.LapTime),
        speed_kmh=ac.getCarState(PLAYER_CAR, acsys.CS.SpeedKMH),
        gear=ac.getCarState(PLAYER_CAR, acsys.CS.Gear),
        session=SessionInfo(
            session_type=memory.graphics.get("session"),
            total_laps=memory.graphics.get("numberOfLaps"),
            time_left_ms=memory.graphics.get("sessionTimeLeft"),
            is_timed_race=bool(memory.static.get("isTimedRace")),
            has_extra_lap=bool(memory.static.get("hasExtraLap")),
        ),
    )


def describe_session(frame):
    session = frame.session
    return "session={} laps={} time_left_ms={:.0f} timed_race={} extra_lap={} fuel={:.2f}".format(
        session.session_type, session.total_laps, session.time_left_ms,
        session.is_timed_race, session.has_extra_lap, frame.fuel)
