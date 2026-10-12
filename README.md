# AC Modding Starter

A starting point for writing Python tools for Assetto Corsa (the 2014
Kunos sim, not Assetto Corsa EVO — see note below) as portfolio
projects. Two working "hello world" examples, plus a deploy helper.

## What's here

```
apps/python/hello_hud/     an in-game HUD app (AC's embedded Python)
apps/python/fuel_hud/      in-game fuel HUD: tank, laps left, fuel to the flag, lap budget
telemetry/                 an external telemetry reader (your normal Python)
scripts/deploy_app.py      copies an app folder into your AC install for testing
tests/                     pytest suite for the game-independent logic
```

### `apps/python/hello_hud`

Runs *inside* Assetto Corsa, using the game's own restricted Python
3.3 runtime and its `ac` / `acsys` modules. Good for HUD widgets and
anything that needs to draw over the game. No pip, no network,
stdlib-only. Read the comments at the top of `hello_hud.py` — they
explain the app lifecycle (`acMain` / `acUpdate` / `acShutdown`) that
AC expects.

### `apps/python/fuel_hud`

An in-game fuel window:

| Row | Example | Meaning |
|---|---|---|
| Tank | `51.80 L` | Fuel in the tank |
| Laps left | `12.6` | How long the tank lasts at the average |
| To flag | `-4.00 L (-1.0 laps)` | Fuel left over at the flag at the average. Green: a lap or more spare. Amber: under a lap spare. Red: you run dry first |
| Target | `3.81 L/lap` | The most you can use per lap and still reach the flag |
| This lap | `1.73 L (+0.04)` | Fuel used so far, and how far over (+) or under (-) the target budget for this point of the lap. Green: on or under budget. Amber: up to 2% of the target over. Red: more |
| Last lap | `4.08 L` / `4.31 L (pit)` | Fuel used on the previous lap |
| Average | `4.11 L (5 laps)` | Mean of the last 5 laps that count |

Laps are left out of the averages (and labelled on the HUD) when
they're the first lap, include a pit-lane visit or a refuel, or when
the app started watching mid-lap.

"To flag" and "Target" need to know where the flag is. In a lap race
that's the race length. In a timed race, practice or qualifying it's
the session clock divided by your average lap time, so these rows
show `--` until the first lap that counts. Hotlap sessions have no
flag.

The "This lap" budget is spread over the lap following the fuel
profile of your last valid lap, not evenly. Straights burn more than
corners, so an even split would flag every straight as overspending.

`ac.getCarState()` has no fuel value and nothing in the `ac` API
gives the session length, so the app reads both from AC's shared
memory with `mmap` + `struct` (both built into AC's Python), with no
bundled `_ctypes.pyd`. The byte offsets live in `ac_memory.py`, and a
test checks them against the ctypes structs in
`telemetry/shared_memory.py`. All lap bookkeeping and race maths live
in `fuel_logic.py`, which has no game calls and is covered by pytest.

Fuel only drops if fuel consumption is enabled: in Content Manager,
Drive → Assists → Fuel consumption, set to 1× (`FUEL_RATE` in
`Documents\Assetto Corsa\cfg\assists.ini`). At 0 every lap reads
0.00 L.

### `telemetry`

Runs *outside* the game, as a completely normal Python process — any
Python version, any library, pip works fine. It reads AC's live
telemetry via Windows shared memory. This is the approach a project
like an AI race engineer needs, since it can call APIs, run
text-to-speech, etc. — things the in-game runtime can't do.
`shared_memory.py` has a longer accuracy note at the top worth
reading before you extend the struct definitions.

## Quickstart

1. Install Assetto Corsa (Steam) and Content Manager if you haven't —
   Content Manager isn't required but makes launching practice
   sessions and installing apps much less tedious than the stock
   launcher.
2. Deploy the example HUD app:
   ```
   python scripts/deploy_app.py hello_hud
   ```
   (pass `--ac-dir` if it can't find your install automatically)
3. In AC: Options > General > enable `hello_hud` in the apps list.
4. Start any practice session — the HUD should appear showing speed
   and gear.
5. With a session running, in a separate terminal:
   ```
   cd telemetry
   python hello_telemetry.py
   ```
   You should see live speed/gear/lap data printing.

## Tests

The game-independent logic (anything without `ac.*` calls) is tested
with pytest on a normal Python install:

```
pip install -r requirements-dev.txt
python -m pytest
```

`tests/test_py33_compat.py` also checks every file under
`apps/python/` for syntax AC's Python 3.3 can't run (f-strings,
walrus, etc.), since modern Python would otherwise run those files in
tests without complaint.
