# PULSE — Current Build Status

> **Project:** PULSE — a privacy-first, open-source desktop wellbeing companion  
> **Audience:** ADHD / autistic minds  
> **Platform:** Windows 11 (packaged .exe via PyInstaller + Inno Setup)  
> **Repo:** `space-divergentfutures/pulse` (public, AGPL-3.0)  
> **Status:** All 13 build steps complete + data export + reading sessions shipped. 288 tests passing. Packaged exe ships.  
> **Changelog:** see `CHANGELOG.md` for user-facing history.

---

## What PULSE is

A small, always-on-top corner widget that sits near the system clock and counts down your active work time. When the countdown reaches zero it asks you to take a short break — movement suggestion, hydration reminder, optional meal check. Everything is honour-based. No lock by default. The app stores only aggregates and self-reported ratings; no window titles, no keystrokes, no screenshots.

Core philosophy: **the system tracks state, not you.** PULSE is a mirror, not a tracker — every feature serves reflection, not surveillance or compulsion. Explicitly non-diagnostic. Hard-lock (when enabled) is escapable and says so.

---

## Tech Stack

| Layer | Choice |
|---|---|
| Language | Python 3.12.10 |
| UI framework | pywebview 6.2.1 (WebView2 backend) |
| UI content | HTML / CSS / JS — static files, no bundler |
| Tray | pystray 0.19.5 + Pillow 12.3.0 |
| Win32 (idle, lock, startup) | pywin32 312 |
| Storage | SQLite (WAL mode), stdlib `sqlite3` |
| Config | PyYAML 6.0.3 (machine plumbing only; all user settings in SQLite) |
| Packaging | PyInstaller one-dir + Inno Setup installer |
| Tests | pytest 9.1.1 (mocked-clock unit tests) |
| Sync (optional, off by default) | PocketBase over Tailscale; token from env var only |

**Key constraint:** pywebview's frameless window on Windows has ~16px width + ~39px height of invisible WebView2 chrome. Transparency is unreliable on Windows — all cards use opaque dark backgrounds with CSS rounded corners. This was proven and documented in the Step 0 spike before anything else was built.

---

## Architecture

```
pulse/
├── app.py                  # Orchestrator — wires presence → engine → UI
├── config.py               # TimingConfig dataclass (spec defaults)
├── content.py              # Movement suggestions + hydration prompts
├── dayplan.py              # Day plan + reading session scheduling (pure functions)
├── export.py               # Local CSV/JSON data export + manifest
├── machine_config.py       # config.yaml loader (DB path, sync URL)
├── meal.py                 # Meal window definitions + active_window_now()
├── presence.py             # PresenceState derivation (ACTIVE / IDLE / AWAY / LOCKED)
├── reflection.py           # Graph payloads, weekly summaries, pattern detection
├── settings.py             # Settings catalogue, profiles, explainers
├── state_machine.py        # SessionEngine — pure tick() function, mocked-clock safe
├── storage.py              # PulseStorage — all SQLite access
├── sync.py                 # Optional PocketBase sync (off by default)
├── theme.py                # CSS variable injection per appearance setting
├── training.py             # Exercise/Big Break picker + payload builders
├── platform/
│   ├── base.py             # PlatformInterface (abstract)
│   └── windows.py          # Win32: idle, session lock, work area, startup, fullscreen
├── ui/
│   ├── break_card.py       # BreakCard controller + _BreakBridge (js_api)
│   ├── checkin.py          # CheckinCard controller
│   ├── dayplan.py          # DayPlanCard controller ("how long are you here?")
│   ├── firstrun.py         # FirstRunWindow controller
│   ├── insights.py         # InsightsWindow controller
│   ├── settings_window.py  # SettingsWindow controller
│   ├── tray.py             # PulseTray (pystray, background thread)
│   ├── training_card.py    # TrainingCard controller
│   ├── widget.py           # CornerWidget controller + _WidgetBridge (js_api)
│   └── web/                # Static HTML/CSS/JS for every window
│       ├── widget.*        # Corner countdown widget
│       ├── break_card.*    # Light break card (movement + meal + detail + reading)
│       ├── dayplan.*       # Day plan card (start-of-day hours picker)
│       ├── checkin.*       # Block rating + context
│       ├── training_card.* # Training session card + Big Break
│       ├── insights.*      # Weekly graph + unlock meter
│       ├── settings.*      # Settings panel
│       └── firstrun.*      # Guided first-run wizard
├── data/
│   ├── exercises.json      # Exercise library (6 categories, 3 levels each)
│   └── big_break.json      # 12-min Big Break options
tests/
├── conftest.py             # Mocked-clock helpers
├── test_state_machine.py   # Engine tick, transitions, suspend gap
├── test_accumulators.py    # All time accumulators
├── test_config.py          # TimingConfig validation
├── test_focus.py           # Focus Guard logic
├── test_insights.py        # Graph + weekly payload
├── test_meal.py            # Meal window detection + storage
├── test_packaging.py       # PyInstaller artifact checks
├── test_reflection_s9.py   # Stage 2/3 unlock + useful-check cadence
├── test_settings.py        # Settings + profiles
├── test_storage.py         # All SQLite operations
├── test_sync.py            # PocketBase sync (mocked HTTP)
├── test_theme.py           # CSS variable generation
├── test_training.py        # Exercise picker + progression
├── test_tray.py            # Tray menu callbacks
└── test_windows_idle.py    # Win32 idle detection (mocked ctypes)
```

---

## What's Built (all 13 steps done)

### Step 0 — Corner widget spike (the gate)
Proved pywebview frameless + always-on-top works on Windows. Transparency is unreliable; opaque card baseline chosen. Documented in `spike/SPIKE-NOTES.md`.

### Step 1 — Presence + state machine
- `PresenceState`: ACTIVE (< 60 s idle), IDLE (≥ 60 s, pauses accumulator), AWAY (≥ 10 min idle or LOCKED)
- Win32 idle via `GetLastInputInfo` / `GetTickCount64` (64-bit, no 49-day wrap issue)
- Session lock via `WTSRegisterSessionNotification` polling fallback
- `SessionEngine.tick(now_ms, idle_seconds, locked)` — pure, mocked-clock testable
- State machine: `WORK → WARN → BREAK → WORK`
- Suspend-gap detection: poll gap > 60 s → treat as AWAY (no silent laptop-nap accumulation)

### Step 2 — Production corner countdown widget
- Bottom-right, near system clock, frameless, always-on-top
- Phase states: `countdown | due | timer | done | training`
- Deadline-based JS tick (wall-clock deadline, not decrement) — **recently fixed**; upward corrections from idle noise are ignored so the display never ticks backward
- "Break now" button → Python callback via `js_api`
- Escalation (amber pulse) once countdown hits zero
- Focus Guard suppresses escalation

### Step 3 — Light movement layer
- 30-min active-time interval (configurable 10–90 min)
- 5-min advance warning countdown (configurable 0.5–15 min)
- 90-second self-started break timer (honour-based, JS-owned wall-clock)
- Away reset: real step-away resets the short-break accumulator
- Movement suggestions rotate from a content list; hydration prompt rides on every break

### Step 4 — Reflection Stage 1 + SQLite + unlock meter
- SQLite `pulse.db` (WAL mode, UUID PKs, `machine_id`)
- One-tap block rating after every break (1–10, faces, or labelled words)
- Graph updates live immediately after rating
- Unlock meter: 15 non-skipped ratings to unlock pattern insights (evidence floor)
- Skipping is logged without guilt; a skip doesn't block the meter

### Step 5 — Settings + profiles + explainers + first-run
- Every user-facing setting lives in SQLite (not a config file)
- 18 settings across 8 groups: Light breaks, Training breaks, Reflection, Body floor, Appearance, System, Sync, Focus Guard
- Every setting has a three-part explainer: *what it does*, *who it tends to suit*, *the trade-off* — framed non-clinically, never "if you have X"
- 5 preference profiles (tunable starting points, NOT diagnoses):
  - Long ramp / protect focus
  - Frequent gentle nudges
  - High predictability
  - Firm accountability
  - Minimal / just movement
- Guided first-run wizard: core choices once, with explainers, then done

### Step 6 — Meal windows
- Configurable meal windows (default: lunch 11:30–14:00)
- First break inside a meal window asks "Have you eaten today?"
- **State A:** "Yes, I'm good" → **State C (new):** food/water detail chips → break
- **State B:** "Not yet" → duration picker (10–45 min) → extended food break
- "Not now — remind me next break" defers (fires again next break)
- Once answered yes/no, the window is settled for the day
- Detail chips (added recently):
  - Food: Light snack / Medium meal / Heavy meal
  - Water: A little / A glass / Plenty
  - "Continue break" sends selections to Python; "skip details" proceeds without
  - Stored in SQLite `food_detail` + `water_amount` columns (added via safe `ALTER TABLE` migration)

### Step 7 — Boundary / training layer + Big Break
- 90-min active-time boundary accumulator (configurable)
- Exercise library: 6 categories, 3 levels each (auto-progressess after 6 clean completions, auto-deloads after 2 consecutive skips, pain cooldown available)
- Categories: Hinge/Power, Push, Pull, Squat/Lunge, Core/Stability, Carry/Loaded Walk
- Training session: get-ready screen → 2-exercise pair → outcome tap per exercise
- Big Break (12 min): optional "go outside" alternative to a training session
- Daily cap: 2 training sessions/day by default (configurable 0–4)
- Hard-lock option (off by default): honest full-screen wall, escapable, says so

### Step 8 — Focus Guard
- Manual toggle in settings (off by default)
- While active: corner countdown never escalates, never pulses
- Training breaks deferred to next natural break edge, not dropped
- Wave-off button appears to dismiss the widget without starting a break
- Body floor (hydration, meal windows) still fires on any break that does land

### Step 9 — Reflection Stages 2–3 + useful-check cadence
- Stage 2 unlocks after 5 non-skipped ratings across 3+ distinct days → block type prompt
- Stage 3 unlocks after 5 additional check-ins with block type filled → note prompt
- "Was this useful?" check fires after every 5.5 accumulated active hours (persists across days, carries the remainder — never resets at midnight)
- Stage 2+ only (no point asking before block types exist)
- Graph updates live after context step

### Step 10 — Weekly Insights view + unlock meter reveal
- Weekday bar chart (Mon–Sun), per-day average rating
- Pattern detection: cross-patterns behind the evidence floor (15 observations)
- Hedged, floored phrasing: "on your data so far…", never a diagnosis or placement
- Unlock meter visible progress bar toward the evidence floor
- Insights window accessible from the tray

### Step 11 — Tray + HKCU startup
- System tray icon with menu: Pause/Resume, Break now, Insights, Settings, Quit
- Today's training count shown in tray tooltip
- HKCU Run key startup (per-user, no admin required) — off by default; synced on settings change
- Pause suppresses all break events (AWAY_RESET still clears pending state)

### Step 12 — Optional PocketBase sync
- Off by default; zero data leaves the machine unless explicitly configured
- Requires: `sync_enabled = true` in settings + `sync_url` in `config.yaml` + `PULSE_PB_TOKEN` in environment
- `PULSE_PB_TOKEN` comes from env var ONLY — never hardcoded, never stored in any file
- `sync_url` must be a Tailscale address — never internet-exposed
- Syncs `checkins` and `breaks` tables; remote rows received from other machines are inserted `ON CONFLICT IGNORE` (local rows are never overwritten)
- Retry queue: any row not in `sync_log` is re-attempted next cycle

### Post-13 — Reading sessions / day plan (shipped)
- First active moment of each day: corner card asks "How long are you at the desk today?" (+/- picker, half-hour steps, "not today" skip)
- Planned day ≥ 4 h (configurable `reading_min_day_hours`) → a reading session (default 30 min, configurable `reading_session_minutes`) is scheduled at the **midpoint** of the planned window (wall-clock)
- When due, the corner widget shows "Reading break — whenever you're ready" (same offer pattern as training); the next break the user starts becomes the reading break ("Grab your book", self-started timer, hydration rides)
- Honour-based; recorded in `breaks` with layer `reading` (does NOT count toward the training cap) and settled in the new `day_plans` table
- Focus Guard: offer stays quiet, pending flag still routes the next natural break to reading
- Survives restarts (plan persists in SQLite); expires naturally at midnight
- Pure scheduling maths in `pulse/dayplan.py` (mocked-clock testable); new UI: `ui/dayplan.py` + `web/dayplan.*`
- Also fixed in this pass: the widget's training-ready "Do it" button was routed to an unwired callback (dead unless the countdown had taken the card over) — training/reading clicks now route through `break_now`

### Post-13 — Data export (shipped)
- Settings → "Your data": export to CSV or JSON, all data or last 30/90 days
- Tables: `checkins`, `breaks`, `meal_prompts`, `active_time` (whitelist enforced in `storage.fetch_table`; meta/settings/sync internals never exportable)
- Native folder dialog (pywebview `FOLDER_DIALOG`); files written locally, nothing sent anywhere
- Epoch `ts` columns get a derived human-readable `ts_iso` column so CSVs open cleanly in spreadsheets
- Cutoff filtering respects the schema's mixed time types: epoch floats for `checkins`/`breaks`, ISO dates for `meal_prompts`/`active_time`
- `PULSE_EXPORT_README.txt` manifest explains every column and restates the privacy floor
- 10 tests in `tests/test_export.py` against the real storage layer

### Step 13 — Packaging + polish
- PyInstaller one-dir build, `PULSE.spec` defines web assets as `datas`
- Inno Setup installer (`installer/pulse.iss`)
- WebView2 runtime check on launch (friendly message if missing)
- `run_pulse.py` entry point for development
- `SETTINGS.md` documents every setting for users
- README covers SmartScreen note, Wayland caveat, non-diagnostic stance
- AGPL-3.0 licence + third-party notices

---

## SQLite Schema (`pulse.db`)

```sql
meta                  -- key/value store (machine_id, useful_check_ms, ...)
active_time           -- daily active minutes per machine (summed at display, never merged)
checkins              -- block ratings: id, machine_id, ts, day, rating, block_type, energy, note, skipped
meal_prompts          -- id, machine_id, date, window, answered, extended_minutes, food_detail, water_amount
day_plans             -- id, machine_id, date, planned_hours, reading_at, reading_done, ts
breaks                -- training/big/light break log: id, machine_id, ts, day, layer, enforcement, outcome, duration_s
exercise_progress     -- per-exercise level (1/2/3), clean_streak, consec_skips, pain_until
settings              -- all user-facing settings as JSON strings
tracked_dimensions    -- which reflection dimensions are enabled per machine
sync_log              -- records successfully pushed to PocketBase (retry queue)
```

All rows have UUID PKs. Multi-machine merge is safe: records from different `machine_id` values never collide; daily totals are summed at display, never overwritten.

---

## Settings Catalogue

| Key | Default | Group |
|---|---|---|
| `enforcement_light` | corner_countdown | Light breaks |
| `enforcement_training` | session_card | Training breaks |
| `snooze_light` | off | Light breaks |
| `timing_mode` | dynamic | Light breaks |
| `warning_lead_minutes` | 5 min | Light breaks |
| `light_interval_minutes` | 30 min | Light breaks |
| `light_break_seconds` | 90 s | Light breaks |
| `max_training_sessions_per_day` | 2/day | Training breaks |
| `training_enabled` | true | Training breaks |
| `tracking_enabled` | true | Reflection |
| `meal_windows_enabled` | true | Body floor |
| `reading_enabled` | true | Reading |
| `reading_session_minutes` | 30 min | Reading |
| `reading_min_day_hours` | 4 hrs | Reading |
| `rating_scale_style` | numbers | Reflection |
| `appearance_theme` | dark | Appearance |
| `appearance_accent` | teal | Appearance |
| `appearance_font_size` | normal | Appearance |
| `appearance_font` | default | Appearance |
| `start_with_windows` | false | System |
| `sync_enabled` | false | Sync |
| `focus_mode_enabled` | false | Focus Guard |

---

## Preference Profiles

| Key | Blurb |
|---|---|
| `long_ramp` | 45-min interval, countdown only, dynamic — deep work runway |
| `frequent_gentle` | 20-min interval, soft overlay, one snooze — stay loose |
| `high_predictability` | Fixed timing, 10-min warning, 30-min interval — no surprises |
| `firm_accountability` | Hard-lock on both layers, snooze off — for when softer prompts get overridden |
| `minimal_movement` | No training layer, no tracking — purely light movement nudges |

---

## Privacy Constraints (hard rules)

- No window titles stored
- No keystrokes stored
- No screenshots
- No app names stored
- Only aggregates (time counters) and self-reported ratings
- `PULSE_PB_TOKEN` from environment variable ONLY — never hardcoded, never in any file
- `sync_url` must be a Tailscale address — never internet-exposed
- Hard-lock is escapable and the UI says so
- Non-diagnostic language throughout — "tends to suit people who…", never "pick this if you have X"

---

## Known Bugs Fixed This Session

| Bug | Root Cause | Fix |
|---|---|---|
| Meal buttons (Yes / Not yet) did nothing | `.card { display: flex }` in author CSS beats browser's `[hidden] { display: none }` user-agent rule | Added `[hidden] { display: none !important; }` to all card CSS files |
| Countdown ticked backward (6:13 → 6:08 → 6:13) | JS decremented wall-clock every second; Python pushed active-time remaining which is higher after an idle period | JS now stores a `countdownEndAt` deadline (ms epoch); derives display from `(deadline - Date.now()) / 1000`; ignores Python pushes that would move the deadline later |

---

## Test Coverage

288 tests, all passing. Mocked-clock design means timing bugs are caught deterministically without real sleeps.

```
test_dayplan.py           # Reading scheduling maths + day_plans storage
test_export.py            # Data export: whitelist, cutoff types, CSV/JSON, manifest
test_state_machine.py     # Engine tick, all transitions, suspend-gap, tick-wrap
test_accumulators.py      # Short-break, boundary, lifetime, useful-check counters
test_config.py            # TimingConfig validation (interval/warning constraints)
test_focus.py             # Focus Guard: escalation suppression, training deferral
test_insights.py          # Graph payload, weekly grouping, pattern detection
test_meal.py              # Meal window time math, storage, settled logic
test_packaging.py         # PyInstaller build artifact checks
test_reflection_s9.py     # Stage 2/3 unlock conditions, useful-check cadence
test_settings.py          # Settings read/write, profiles, first-run
test_storage.py           # All SQLite CRUD, migration, UUID PK, WAL
test_sync.py              # PocketBase sync (mocked HTTP)
test_theme.py             # CSS variable generation per theme/accent
test_training.py          # Exercise picker, progression engine
test_tray.py              # Tray menu callbacks
test_windows_idle.py      # Win32 idle detection (mocked ctypes)
```

---

## Known Limitations

- **Windows 11 only** for the full feature set — idle detection, session lock, and startup are Win32. pywebview itself supports macOS/Linux, but those platform adapters don't exist yet.
- **WebView2 runtime dependency** — checked on launch with a friendly message, but still a hurdle on locked-down machines.
- **Static exercise / Big Break content** — `exercises.json` and `big_break.json` are not user-editable yet.
- **Meal window times defined in code** (`meal.py`) — not yet editable in Settings.
- **No voice/audio cues** — people working in exclusive-fullscreen apps can miss the corner widget.
- **SmartScreen warning** on first launch of unsigned builds (normal for small open-source tools; documented in README).

## Accessibility Notes (honest state)

- High-contrast dark and light themes, 4 font sizes (88%–135%), 3 font families — all system fonts
- Low-pressure, non-clinical language throughout; skips logged without guilt
- Honour-based design reduces executive-function pressure by default
- **Not yet done:** a proper screen-reader/ARIA audit, reduced-motion option, full keyboard-navigation pass. These are real gaps, not solved problems.

## What Could Come Next (prioritised)

**High value / lower effort**
- ~~Data export (CSV/JSON)~~ — **SHIPPED** (see Post-13 section above)
- Per-user meal window time editing in Settings
- Simple exercise disable/toggle UI (full custom library later)
- Linux idle adapter — the big unlock for open-source reach
- Streaks / simple habit counters in Insights (data already exists)

**Medium effort**
- Richer Big Break content (rotating or expandable)
- Optional voice / system audio cue for breaks
- macOS platform layer
- Export/import flow for manual multi-machine use (fallback when Tailscale isn't wanted)

**Longer term**
- Android companion (local-first)
- Custom exercise library with progression rules exposed
- Additional reflection dimensions behind the same evidence floor
- Accessibility: ARIA/screen-reader audit, reduced-motion toggle
