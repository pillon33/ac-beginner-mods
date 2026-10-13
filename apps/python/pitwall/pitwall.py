"""
pitwall.py — the Pitwall in-game app: one AC app, one window per stat
(fuel, car, ...).

HOW AC RUNS THIS FILE
----------------------
AC imports this module and calls three functions itself:

  acMain(ac_version)  once when the app is activated: create windows
  acUpdate(deltaT)    once per rendered frame, for the whole app
  acShutdown()        once when AC closes or the app is deactivated

`ac` and `acsys` only exist inside AC's embedded Python 3.3 (no pip,
no ctypes, no f-strings).

HOW IT'S SPLIT
---------------
Every frame: read the game once into a Frame (pitwall_hud.ac_frame),
update the shared RaceState, then let each window render from it.
All logic lives in pitwall_core, which has no `ac` calls and is
covered by pytest; scripts/deploy_app.py copies it in next to this
file. This file and pitwall_hud only move data between AC and that
logic.

Window definitions (rows, readouts) are in pitwall_core/windows.py.
"""

import os
import sys
import traceback

import ac

# AC imports this file with the AC install folder as the working
# directory, so make the packages beside it importable explicitly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pitwall_core.memory import SharedMemory  # noqa: E402
from pitwall_core.state import RaceState  # noqa: E402
from pitwall_core.windows import WINDOWS  # noqa: E402
from pitwall_hud.ac_frame import describe_session, read_frame  # noqa: E402
from pitwall_hud.stat_window import StatWindow  # noqa: E402

APP_NAME = "pitwall"

memory = None
state = RaceState()
windows = []
failed_windows = set()
logged_session = False


def log(message):
    ac.log("{}: {}".format(APP_NAME, message))


def acMain(ac_version):
    global memory
    try:
        memory = SharedMemory()
    except Exception:
        log("could not open shared memory:\n{}".format(traceback.format_exc()))

    for spec in WINDOWS:
        windows.append(StatWindow(spec))

    log("acMain finished, {} windows".format(len(windows)))
    return APP_NAME


def acUpdate(deltaT):
    global logged_session
    if memory is None:
        return

    frame = read_frame(memory)
    if not logged_session:
        # The offsets come from Kunos' struct layout; log what they
        # read once so a wrong one shows up as an implausible value.
        log(describe_session(frame))
        logged_session = True

    state.update(frame)

    for window in windows:
        try:
            window.render(state)
        except Exception:
            # One broken window mustn't take the others down. Log once,
            # not every frame.
            if window.name not in failed_windows:
                failed_windows.add(window.name)
                log("window {} failed:\n{}".format(window.name, traceback.format_exc()))


def acShutdown():
    if memory is not None:
        memory.close()
    log("acShutdown called")
