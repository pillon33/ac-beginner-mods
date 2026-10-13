# AC Modding Starter

Python tools for Assetto Corsa (the 2014 Kunos sim, not Assetto Corsa
EVO, which has no scripting API) built as a portfolio project:
**Pitwall**, an in-game app with a window per session stat, plus
external telemetry tools that share its logic.

## What's here

```
apps/python/pitwall/       Pitwall, the in-game app: one window per stat (AC's embedded Python 3.3)
pitwall_core/              the logic behind it: pure Python 3.3, no game calls, shared with telemetry/
content/gui/icons/         app-bar icons (placeholders), where AC expects them
telemetry/                 external tools on your normal Python, reading AC's shared memory
scripts/deploy_app.py      copies the app (plus pitwall_core) into your AC install
scripts/gen_layout.py      generates pitwall_core/layout.py from telemetry's ctypes structs
tests/                     pytest suite
```

## Pitwall

One AC app, several windows. Each window has its own entry in AC's
in-game app bar, so you show only the ones you want.

### Fuel window

| Row | Example | Meaning |
|---|---|---|
| Tank | `51.80 L` | Fuel in the tank |
| Laps left | `12.6` | How long the tank lasts at the average |
| To flag | `-4.00 L (-1.0 laps)` | Fuel left over at the flag at the average. Green: a lap or more spare. Amber: under a lap spare. Red: you run dry first |
| Target | `3.81 L/lap` | The most you can use per lap and still reach the flag |
| This lap | `1.73 L (+0.04)` | Fuel used so far, and how far over (+) or under (-) the target budget for this point of the lap. Green: on or under budget. Amber: up to 2% of the target over. Red: more |
| Last lap | `4.08 L` / `4.31 L (pit)` | Fuel used on the previous lap |
| Average | `4.11 L (5 laps)` | Mean of the last 5 laps that count |

Laps are left out of the averages (and labelled) when they're the
first lap, include a pit-lane visit or a refuel, or when the app
started watching mid-lap.

"To flag" and "Target" need to know where the flag is. In a lap race
that's the race length. In a timed race, practice or qualifying it's
the session clock divided by your average lap time, so these rows show
`--` until the first lap that counts. Hotlap sessions have no flag.

The "This lap" budget follows the fuel profile of your last valid lap
rather than an even split: straights burn more than corners, so an
even split would flag every straight as overspending.

Fuel only drops if fuel consumption is on: Content Manager → Assists →
Fuel consumption 1× (`FUEL_RATE` in
`Documents\Assetto Corsa\cfg\assists.ini`).

### Car window

Speed and gear.

### How it's built

```
AC shared memory + ac API
        │  pitwall_hud/ac_frame.py      the only code that reads the game
        ▼
      Frame  ──►  RaceState             one LapTracker + FuelTracker for every window
                     │
                     ▼
        pitwall_core/windows.py         each window's rows and readout: {row: (text, status)}
                     │
                     ▼
        pitwall_hud/stat_window.py      draws labels and colours
```

- **All logic is in `pitwall_core`**: lap bookkeeping, fuel and race
  maths, formatting. It has no `ac` calls, so pytest covers it, and the
  external tools can import the same code. It's written for Python 3.3
  because AC loads it too.
- **One shared state.** The app reads the game once per frame and every
  window renders from the same trackers, so windows can't disagree
  about which lap it is or which laps count.
- **Shared memory without ctypes.** `ac.getCarState()` has no fuel or
  session-length values, and AC's Python ships without ctypes. So
  `pitwall_core/memory.py` reads shared memory with `mmap` + `struct`
  at byte offsets from `layout.py`. That file is generated from the
  ctypes structs in `telemetry/shared_memory.py`, the single
  definition of AC's memory layout, and a test fails if it's stale.
- **Unique package names.** All AC Python apps share one interpreter
  and module cache, so `pitwall_core` and `pitwall_hud` are named to
  avoid colliding with other apps' modules.

Adding a window: write a readout in `pitwall_core/windows.py`, add a
`WindowSpec` to `WINDOWS`, and add `<window>_ON.png` / `_OFF.png`
(64×64) to `content/gui/icons/`. A test checks every window has both.

## telemetry

Runs *outside* the game as a normal Python process (any version, pip
works). It reads AC's shared memory with ctypes, which is the right
place for anything the in-game runtime can't do: logging to disk,
dashboards, LLM calls, text-to-speech. `shared_memory.py` explains
how to extend the structs safely.

## Quickstart

1. Install Assetto Corsa (Steam), and optionally Content Manager.
2. Deploy Pitwall:
   ```
   python scripts/deploy_app.py pitwall
   ```
   (pass `--ac-dir` if it can't find your install automatically)
3. In AC: Options → General → enable `pitwall` in the apps list.
4. Start a session and open the Fuel and Car windows from the app bar
   on the right edge of the screen.
5. With a session running, in a separate terminal:
   ```
   cd telemetry
   python hello_telemetry.py
   ```

## Development

```
pip install -r requirements-dev.txt
python -m pytest
```

- `tests/test_app.py` runs the app's `acMain` / `acUpdate` lifecycle
  with stand-in `ac` modules, so wiring errors show up without
  starting the game.
- `tests/test_py33_compat.py` rejects syntax AC's Python 3.3 can't run
  (f-strings, walrus, ...) in everything AC loads.
- After changing a struct in `telemetry/shared_memory.py`, run
  `python scripts/gen_layout.py`.
