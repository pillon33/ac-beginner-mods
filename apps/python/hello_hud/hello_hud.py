"""
hello_hud.py — a minimal Assetto Corsa in-game Python app.

This is the "hello world" of AC modding: a small floating HUD window
that shows live speed and gear. It exists to teach you the app
lifecycle AC expects, not to be useful on its own.

HOW AC LOADS THIS FILE
-----------------------
AC's built-in Python runtime looks for three specific function names in
this file and calls them itself — you never call them yourself:

  acMain(ac_version)   -> called once when the app is activated.
                           Build your window and labels here, return
                           the app's name.
  acUpdate(deltaT)      -> called every rendered frame. deltaT is the
                           time in seconds since the last call. Read
                           telemetry and update your labels here.
  acShutdown()           -> called once when AC closes or the app is
                           deactivated. Optional — use it to clean up
                           (close files, sockets, etc).

`ac` and `acsys` only exist inside AC's embedded interpreter — this
file will show import errors in any normal Python editor/linter, and
that's expected. You cannot "pip install" anything for it either; it
runs on AC's bundled Python 3.3, sandboxed, stdlib-only.

WHERE THIS FILE HAS TO LIVE
----------------------------
Copy the whole `hello_hud` folder (this file + ui.json) into:

  <AC install dir>\\apps\\python\\hello_hud\\

e.g. on a typical Steam install:
  C:\\Program Files (x86)\\Steam\\steamapps\\common\\assettocorsa\\apps\\python\\hello_hud\\

See scripts/deploy_app.py in this repo for a script that copies it
there for you. Then in-game: Options > General > tick "hello_hud" in
the apps list, and it'll appear next time you're on track.
"""

import ac
import acsys

# Module-level globals for the widgets we create in acMain and update
# in acUpdate. AC re-imports this module fresh each session, so plain
# globals are fine here.
app_window = None
label_speed = None
label_gear = None


def acMain(ac_version):
    global app_window, label_speed, label_gear

    app_window = ac.newApp("hello_hud")
    ac.setSize(app_window, 200, 120)
    ac.setTitle(app_window, "Hello HUD")

    label_speed = ac.addLabel(app_window, "Speed: -- km/h")
    ac.setPosition(label_speed, 10, 40)

    label_gear = ac.addLabel(app_window, "Gear: -")
    ac.setPosition(label_gear, 10, 70)

    # ac.log() writes to Documents\Assetto Corsa\logs\py_log.txt —
    # your main debugging tool since there's no interactive debugger.
    ac.log("hello_hud: acMain finished, app initialised")

    # The string you return becomes the app's internal name.
    return "hello_hud"


def acUpdate(deltaT):
    # focusedCar 0 is always the player's own car.
    car = 0

    speed_kmh = ac.getCarState(car, acsys.CS.SpeedKMH)
    gear = ac.getCarState(car, acsys.CS.Gear)  # 0 = reverse, 1 = neutral, 2+ = 1st, 2nd, ...

    ac.setText(label_speed, "Speed: {:.0f} km/h".format(speed_kmh))
    ac.setText(label_gear, "Gear: {}".format(gear_to_string(gear)))


def acShutdown():
    ac.log("hello_hud: acShutdown called")


def gear_to_string(gear):
    if gear == 0:
        return "R"
    if gear == 1:
        return "N"
    return str(gear - 1)


# NEXT STEPS ONCE THIS RUNS:
#   1. Add a delta-to-best-lap label using acsys.CS.LapTime /
#      ac.getCarState(car, acsys.CS.LapDeltaToSessionBest) (name may
#      differ by CSP version — check the bundled Python doc, see
#      README).
#   2. Colour the speed label red above a redline RPM you read via
#      acsys.CS.RPM.
#   3. Persist a setting (e.g. HUD position) to an .ini file with
#      Python's configparser — this is where you start writing to
#      Documents\Assetto Corsa\cfg\ instead of just reading telemetry.
