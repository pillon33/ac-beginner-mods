# AC Modding Starter

A starting point for writing Python tools for Assetto Corsa (the 2014
Kunos sim, not Assetto Corsa EVO — see note below) as portfolio
projects. Two working "hello world" examples, plus a deploy helper.

## What's here

```
apps/python/hello_hud/     an in-game HUD app (AC's embedded Python)
telemetry/                 an external telemetry reader (your normal Python)
scripts/deploy_app.py      copies an app folder into your AC install for testing
```

### `apps/python/hello_hud`

Runs *inside* Assetto Corsa, using the game's own restricted Python
3.3 runtime and its `ac` / `acsys` modules. Good for HUD widgets and
anything that needs to draw over the game. No pip, no network,
stdlib-only. Read the comments at the top of `hello_hud.py` — they
explain the app lifecycle (`acMain` / `acUpdate` / `acShutdown`) that
AC expects.

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
