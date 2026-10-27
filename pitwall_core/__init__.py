"""
pitwall_core — the logic behind the Pitwall in-game app, shared with
the external tools in telemetry/.

Everything here is pure Python 3.3-compatible code with no `ac`,
`acsys` or ctypes imports, so it runs on AC's embedded interpreter,
on a normal Python, and under pytest. scripts/deploy_app.py copies
this package into the app when deploying.

The name is deliberately specific: all of AC's Python apps share one
interpreter and one module cache, so a generic package name could
collide with another app's module.

  layout     shared memory byte offsets (generated, don't edit)
  memory     reads fields from AC's shared memory with mmap + struct
  laps       LapTracker: lap boundaries, progress, lap times, which laps count
  race       session info and laps to the flag
  fuel       FuelTracker and fuel/strategy maths
  state      Frame (one tick of game data) and RaceState (all trackers)
  display    text formatting and status colours
  windows    what each HUD window shows
"""
