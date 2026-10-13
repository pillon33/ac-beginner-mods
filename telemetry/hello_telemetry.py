"""
hello_telemetry.py — the "hello world" of external AC telemetry
reading. Run this in a normal terminal (any modern Python, any
editor, full pip access) WHILE Assetto Corsa is running with a car on
track. It polls live speed/gear/lap data and prints it.

This is the shape every later external tool (logger, dashboard,
voice-based race engineer) starts from: open shared memory, poll it
in a loop, do something with the numbers.

Usage:
    python hello_telemetry.py
    (Ctrl+C to stop)
"""

import os
import sys
import time

from shared_memory import AC_SESSION_TYPE, AC_STATUS, ACTelemetry

# pitwall_core (the logic the in-game app uses) lives at the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pitwall_core.display import format_gear  # noqa: E402


def main():
    print("Waiting for telemetry... start a session in Assetto Corsa.")
    with ACTelemetry() as telemetry:
        try:
            while True:
                physics, graphics = telemetry.read()

                status = AC_STATUS.get(graphics.status, graphics.status)
                session = AC_SESSION_TYPE.get(graphics.session, graphics.session)

                print(
                    "\r{:>6} | {:>9} | speed {:5.0f} km/h | gear {:>2} | "
                    "rpm {:5d} | lap {:>2} | pos {:>2}".format(
                        status, session, physics.speedKmh,
                        format_gear(physics.gear), physics.rpms,
                        graphics.completedLaps, graphics.position,
                    ),
                    end="",
                    flush=True,
                )
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
