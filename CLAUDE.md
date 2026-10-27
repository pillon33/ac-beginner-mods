# AC Modding Starter — project memory

## What this is

A portfolio project: learning Assetto Corsa (2014 Kunos sim — **not**
Assetto Corsa EVO, which has no Python/scripting API as of its 2026
SDK) modding through Python, building toward an AI race engineer as
the capstone. Owner: Szymon, targeting mid-level SWE roles with AI
tooling exposure — code here should read as portfolio-quality, not
throwaway scripts.

## The one thing to never forget: two separate Python runtimes

This repo mixes code for two completely different execution contexts.
Getting this wrong is the most common mistake when working on it.

| | `apps/python/**` | `telemetry/**` |
|---|---|---|
| Runs | inside AC, on AC's bundled interpreter | as a normal external process |
| Python version | **3.3** — no f-strings (3.6+), limited stdlib | whatever's installed (3.10+ assumed) |
| Packages | stdlib only, **no pip**, **no ctypes** | full pip access |
| Imports `ac` / `acsys` | yes (these modules don't exist outside AC — a linter/IDE will show import errors here, that's expected, not a bug) | no |
| Gets telemetry via | `ac.getCarState(...)`, plus shared memory via `mmap` + `struct` for what `ac` lacks (fuel, session length) | Windows shared memory via ctypes structs, see `telemetry/shared_memory.py` |
| Network / APIs / TTS | not possible | fine |

**Rule of thumb:** if a task needs an LLM call, TTS, a web request, or
any non-stdlib package, it belongs in `telemetry/` (or a new sibling
external-tool folder), never in `apps/python/`. Conversely, drawing an
in-game HUD overlay can only happen in `apps/python/`.

**`pitwall_core/` runs in both:** AC loads it (deployed into the app)
and telemetry/tests import it. It follows the in-game rules (3.3,
stdlib only) and additionally never imports `ac`, `acsys` or ctypes.

**Code style inside `apps/python/**` and `pitwall_core/**`:** use
`.format()` or `%` formatting, not f-strings — an f-string crashes the
app with a syntax error on AC's Python 3.3.
`tests/test_py33_compat.py` catches this.

## In-game runtime facts (verified in-game 2026-10-13, AC + CSP 0.2.11)

- **No ctypes in-game.** AC's Python 3.3.5 has `mmap` and `_struct`
  built in but ships no `_ctypes.pyd`. Read shared memory with
  `struct.unpack_from` at byte offsets (see `pitwall_core/memory.py`);
  don't bundle a `.pyd`.
- **`acsys.CS` is a fixed list.** `<AC install>\apps\python\system\acsys.py`
  is the authoritative list (73 entries). Check it before using any
  `CS.*` name: there is no fuel or session-length entry, and
  `acsys.CS.Fuel`, which circulates online, doesn't exist. CSP adds
  `ac.ext_getFuel` / `ac.ext_getMaxFuel`, which are undocumented and
  unused here.
- **All apps share one interpreter and one `sys.modules`.** Apps load
  alphabetically by folder. A module name imported by two apps
  silently resolves to whichever loaded first. Give shared modules a
  project-unique name, never generic ones like `core` or `utils`.
- **`acUpdate` runs once per app per frame**, however many windows the
  app has.
- **One app can own several windows.** Each `ac.newApp` window gets its
  own app-bar entry and is shown or hidden independently. Its icons are
  `<AC install>\content\gui\icons\<window name>_ON.png` / `_OFF.png`
  (64×64 RGBA; built-ins use a white glyph, on a red disc for `_ON`).
  Built-in names like `CAR_STATS` exist, another reason for prefixes.
  The **title-bar** icon is different: AC draws its built-in logo
  (`content/gui/inapp_aclogo.png`) in every window, with no per-window
  setting. To replace it, hide it with `ac.setIconPosition(window, 0,
  -10000)` and draw a label with `ac.setBackgroundTexture` (see
  `pitwall_hud/stat_window.py`).
- **Don't rely on `ac.addOnAppActivatedListener` /
  `addOnAppDismissedListener`.** They never fired when windows were
  toggled.

## Architecture: one suite app, many windows (decided 2026-10-13)

Goal: a collection of in-game stat displays (fuel, tyres, strategy,
lap times, telemetry). Decision: **one** in-game app with one window
per stat, not one app folder per stat. Strategy needs fuel, tyre and
lap state together, and one app means one lap tracker, one
shared-memory read per frame, and no module collisions.

The app is **Pitwall** (`apps/python/pitwall`). Per frame:
`pitwall_hud/ac_frame.py` reads the game into a `Frame` →
`RaceState.update()` (one `LapTracker` + `FuelTracker` shared by all
windows) → each window's readout in `pitwall_core/windows.py` returns
`{row: (text, status)}` → `pitwall_hud/stat_window.py` draws it.
- **All logic lives in `pitwall_core`** (repo root). `deploy_app.py`
  copies it into the app (or symlinks it with `--link`); telemetry
  imports it directly. `pitwall_hud` is the only code calling `ac`.
- **Memory layout source of truth:** the ctypes structs in
  `telemetry/shared_memory.py`. `scripts/gen_layout.py` generates
  `pitwall_core/layout.py` from them; `tests/test_layout.py` fails if
  it's stale. Never hand-edit offsets.
- **New window:** write a readout in `pitwall_core/windows.py` and add a
  `WindowSpec` to `WINDOWS`, plus its two icons in
  `content/gui/icons/` (a test enforces them). Window names start
  with `pitwall_` (AC window names are global). New state that several
  windows need goes in `RaceState`.
- One broken window is logged once and skipped; the others keep
  drawing.

## Repo layout

```
apps/python/pitwall/pitwall.py       AC entry point (acMain/acUpdate/acShutdown): read frame, update state, render windows
apps/python/pitwall/pitwall_hud/     the only ac-calling code: ac_frame.py (game -> Frame), stat_window.py (WindowSpec -> AC labels)
pitwall_core/                        pure shared logic: layout (generated), memory, laps, race, fuel, state, display, windows
content/gui/icons/                   app-bar icons (<window>_ON/_OFF.png, placeholders); mirrors the AC install path, deploy copies them
telemetry/shared_memory.py           ctypes structs (layout source of truth) + BLOCKS + ACTelemetry, Windows-only
telemetry/hello_telemetry.py         polls ACTelemetry and prints live values; imports pitwall_core
scripts/deploy_app.py                copies (or --link symlinks) apps/python/<name> + pitwall_core into the AC install, plus <name>_*.png icons; --ac-dir or AC_INSTALL_DIR
scripts/gen_layout.py                ctypes structs -> pitwall_core/layout.py (--check to verify)
tests/                               pytest; test_app.py runs the app lifecycle with stand-in ac modules; run: pip install -r requirements-dev.txt && python -m pytest
docs/                                untracked local design notes (fuel dashboard spec), not committed
(no LICENSE yet — removed on purpose while this stays personal/private; add MIT back before sharing publicly)
```

### Shared memory layout accuracy

ctypes field order/type/array length must match Kunos' C structs
byte-for-byte, or later fields silently read garbage. The Kunos SDK
reference folder (`sdk\dev\shared memory\`) is **not** in this
install. The layout was taken from `sim_info.py` in
[albertowd/live-telemetry](https://github.com/albertowd/live-telemetry)
(AC SDK 1.14.3). Live status: physics `fuel`, graphics `session`, and
the static block through `trackConfiguration` (AC 1.16.4, shared
memory 1.7) are confirmed. Graphics `numberOfLaps` / `sessionTimeLeft`
and static `isTimedRace` / `hasExtraLap` are still unconfirmed; check
them in a lap-limited race and a timed session. Pitwall logs what it
reads once per session to `py_log.txt`.

## Environment / paths (user-specific, not portable)

- AC install: `C:\Program Files (x86)\Steam\steamapps\common\assettocorsa`
  (`AC_INSTALL_DIR` is set). Apps deploy to `<AC install>\apps\python\<name>\`.
- AC debug logs: `Documents\Assetto Corsa\logs\py_log.txt` (anything
  passed to `ac.log()`) and `log.txt` (app loading, missing icons,
  lower-level errors). In-game live console: press `Home`.
- Apps must be enabled once per app in AC: **Options → General**
  (stored in `Documents\Assetto Corsa\cfg\python.ini`). An enabled app
  whose folder is gone logs "File ... not found" on every launch.
- **Fuel only drops with fuel consumption on:** Content Manager →
  Assists → Fuel consumption 1× (`FUEL_RATE` in
  `Documents\Assetto Corsa\cfg\assists.ini`; it was 0 on 2026-10-12).
- This repo's source is the source of truth — never hand-edit the
  copy inside the Steam folder; redeploy via `deploy_app.py` instead
  (Steam can wipe unmanaged files under `apps/python/` on verify).

## Roadmap (full guide: the "Pit Wall Roadmap" artifact from this
## conversation — ask Claude to pull it up again if you need the
## reasoning/detail behind any phase, this is just the checklist)

- [x] **FP1 — Fundamentals (Week 1):** first in-game app running
      end to end (`hello_hud`, now Pitwall's Car window), comfortable
      with the deploy/test loop.
- [ ] **FP2 — Telemetry logic (Week 2):** delta-to-best-lap, fuel
      estimate. Fuel estimate and the Pitwall suite refactor are done;
      next is delta-to-best-lap as a new window. Key constraint:
      keep the math in plain functions with no `ac.*` calls inside
      them, so they're unit-testable with pytest.
- [ ] **Quali — External tools (Weeks 3-4):** extend
      `hello_telemetry.py` into a CSV/SQLite logger, then a live
      browser dashboard over a local WebSocket.
- [ ] **Race — AI race engineer (Week 5+):** shared memory → state
      tracker (fuel/tyre/lap trend) → decision layer → voice + HUD
      output. Build a **rules-based v1 first** ("fuel: 3 laps left",
      "box now" from thresholds); only swap in an LLM for the
      decision layer once v1 is reliable — that's the v1→v2 story for
      the portfolio, not one opaque project.
- [ ] **Debrief — Ship it:** zip the app folder, share on OverTake.gg
      (Apps section) and/or as a tagged GitHub release with a README
      + screenshot/GIF. Add the MIT license back in before sharing
      publicly (removed for now, personal-use only). Never bundle
      Kunos car/track assets — code only.

## Conventions

- Business logic (math, decisions) lives in plain, testable
  functions; `ac.*` / shared-memory calls stay at the thin edges that
  wrap them.
- One app/tool per folder, named after what it does (the in-game suite
  is the one deliberate exception, see Architecture).
- Commit messages, README updates, and screenshots matter here more
  than in a typical side project — this repo is meant to be read by
  someone hiring, not just to work.
- Verify unknown in-game behaviour with a small throwaway app (deploy,
  drive, read `py_log.txt`) before building on it, and delete it after.

## Working with GitHub (read this before touching git/GitHub here)

- **Repo:** `pillon33/ac-pitwall-mod` on github.com, remote `origin`,
  default branch `main`. Renamed from `ac-beginner-mods` on 2026-10-27;
  GitHub redirects the old URL, but use the new one.
- **Workflow:** Claude does not push directly to `main`. For any
  change: create a branch, push to it, open a pull request, and let
  Szymon review/merge. (One early exception — a direct push to `main`
  — happened before this convention was agreed; everything since
  follows the branch+PR flow.)
- **One branch per PR.** Never push follow-up commits to a branch
  whose PR is already merged; start a new branch from `origin/main`.
- **How Claude reaches GitHub:** in Claude Code sessions, local `git`
  works (commit and push from the session's worktree). Open PRs with
  the GitHub MCP `create_pull_request` tool (`gh` isn't installed).
  In claude.ai chat sessions there's no shell, so use the MCP tools
  for everything.
- **Worktree gotcha:** a branch checked out in a Claude worktree
  (`.claude/worktrees/...`) can't be switched to in Szymon's main
  checkout. After pushing, detach the worktree (`git switch --detach`)
  so he can check the branch out.

### Known gotcha: connector write calls can 403

The GitHub MCP connector has a **known, currently-open Anthropic bug**
([anthropics/claude-ai-mcp#822](https://github.com/anthropics/claude-ai-mcp/issues/822)):
reads succeed, but writes (`create_or_update_file`, `push_files`,
`create_branch`, `issue_write`, ...) can fail with
`403 Resource not accessible by integration`, even with valid OAuth
and push access. Repo settings can't fix it.

**Fix that worked for this repo:** install the separate **"Claude"
GitHub App** (`github.com/apps/claude`, distinct from the OAuth-based
"Claude Github MCP Connector") with access to `ac-pitwall-mod`, then
retry; propagation can take a moment. If fresh 403s appear in a later
session, first check the app is still installed with access to this
repo.
