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
| Packages | stdlib only, **no pip** | full pip access |
| Imports `ac` / `acsys` | yes (these modules don't exist outside AC — a linter/IDE will show import errors here, that's expected, not a bug) | no |
| Gets telemetry via | `ac.getCarState(...)` calls | Windows shared memory (mmap), see `telemetry/shared_memory.py` |
| Network / APIs / TTS | not possible | fine |

**Rule of thumb:** if a task needs an LLM call, TTS, a web request, or
any non-stdlib package, it belongs in `telemetry/` (or a new sibling
external-tool folder), never in `apps/python/`. Conversely, drawing an
in-game HUD overlay can only happen in `apps/python/`.

**Code style inside `apps/python/**`:** use `.format()` or `%`
formatting, not f-strings — an f-string crashes the app with a
syntax error on AC's Python 3.3.

## Repo layout

```
apps/python/hello_hud/hello_hud.py   in-game HUD app: shows live speed + gear
apps/python/hello_hud/ui.json        optional metadata AC/Content Manager can display (name, author, version, description) — not required for the app to function
telemetry/shared_memory.py           ctypes structs (SPageFilePhysics, SPageFileGraphic) + ACTelemetry class that opens AC's "Local\acpmf_physics" / "Local\acpmf_graphics" mmap blocks, Windows-only
telemetry/hello_telemetry.py         polls ACTelemetry in a loop, prints status/session/speed/gear/rpm/lap/position — the external "hello world"
scripts/deploy_app.py                copies (or --link symlinks) an apps/python/<name> folder into a real AC install for playtesting; reads --ac-dir or AC_INSTALL_DIR env var, falls back to common Steam paths
README.md, .gitignore
(no LICENSE yet — removed on purpose while this stays personal/private; add MIT back before sharing publicly)
```

### `shared_memory.py` accuracy note

`ctypes.Structure` field order/type/array-length must match Kunos'
C struct byte-for-byte or later fields silently read garbage (no
error, just wrong numbers/NaNs). The structs here only cover the
long-stable, widely-republished subset (speed, gear, rpm, fuel, gas,
brake from physics; status, session, completedLaps, position, lap
times from graphics). Before adding fields (tyre temps, damage,
flags, the static-info block), cross-check against the reference
Kunos ships in the game install at `<AC install>\sdk\dev\shared
memory\`, and sanity-check with `ctypes.sizeof(...)` against the size
that reference states.

## Environment / paths (user-specific, not portable)

- AC apps deploy to `<AC install>\apps\python\<name>\` — install path
  varies per machine, pass via `--ac-dir` or set `AC_INSTALL_DIR`.
- AC debug logs: `Documents\Assetto Corsa\logs\py_log.txt` (anything
  passed to `ac.log()`) and `log.txt` (lower-level errors). In-game
  live console: press `Home`.
- Apps must be manually enabled once per app in AC: **Options →
  General**, before they appear on track.
- This repo's source is the source of truth — never hand-edit the
  copy inside the Steam folder; redeploy via `deploy_app.py` instead
  (Steam can wipe unmanaged files under `apps/python/` on verify).

## Roadmap (full guide: the "Pit Wall Roadmap" artifact from this
## conversation — ask Claude to pull it up again if you need the
## reasoning/detail behind any phase, this is just the checklist)

- [x] **FP1 — Fundamentals (Week 1):** first in-game app running
      end to end (`hello_hud`), comfortable with the deploy/test loop.
      Next: add a shift light + lap counter, push to GitHub.
- [ ] **FP2 — Telemetry logic (Week 2):** delta-to-best-lap, fuel
      estimate. Key constraint: keep the math in plain functions with
      no `ac.*` calls inside them, so they're unit-testable with
      pytest (the `ac` module doesn't exist outside the game, so
      anything that calls it directly can't be tested that way).
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
- One app/tool per folder, named after what it does.
- Commit messages, README updates, and screenshots matter here more
  than in a typical side project — this repo is meant to be read by
  someone hiring, not just to work.

## Working with GitHub (read this before touching git/GitHub here)

- **Repo:** `pillon33/ac-beginner-mods` on github.com, remote `origin`,
  default branch `main`.
- **Workflow:** Claude does not push directly to `main`. For any
  change: create a branch, push to it, open a pull request, and let
  Szymon review/merge. (One early exception — a direct push to `main`
  — happened before this convention was agreed; everything since
  follows the branch+PR flow.)
- **How Claude reaches GitHub:** through the connected GitHub MCP
  tools (`create_branch`, `push_files`, `create_pull_request`, etc.),
  not local shell — this environment has no `git`/shell access to
  Szymon's machine. Local, non-Claude commits/pushes on Szymon's side
  go through his own terminal as normal.

### Known gotcha: connector write calls can 403

The GitHub MCP connector has a **known, currently-open Anthropic bug**
(see [anthropics/claude-ai-mcp#822](https://github.com/anthropics/claude-ai-mcp/issues/822)):
reads succeed, but writes (`create_or_update_file`, `push_files`,
`create_branch`, `issue_write`, ...) can fail with:

```
403 Resource not accessible by integration
```

even though the OAuth authorization looks fine and the user has push
access. This is **not** fixable via the repo's own settings
(branch protections, collaborator access, etc.) — it's the connector
integration itself lacking write scope.

**Fix/workaround that resolved it for this repo:** install the
separate **"Claude" GitHub App** (`github.com/apps/claude` — distinct
from "Claude Github MCP Connector", which is the OAuth-based one that
hits this bug) and grant it access to this repository:

1. `github.com/apps/claude` → **Install** (or **Configure** if already
   installed) → select `pillon33` → grant access to
   `ac-beginner-mods` (or all repos).
2. Retry the write call. It may take a short moment after installing
   for GitHub to propagate the new installation — if the very first
   retry still 403s, wait briefly and try again before assuming it's
   broken.

If writes start failing again in a future session (fresh 403s on
`create_branch`/`push_files`/etc.), check first whether the "Claude"
GitHub App is still installed with access to this repo before
assuming it's a new problem — this bug is the most likely explanation.
