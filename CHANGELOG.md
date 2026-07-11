# PULSE Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Fixed
- **Sitting-anchored day plan** — the desk-time question and reading schedule were
  anchored to calendar midnight, so a session crossing 12am could consume the next
  morning's question, or a real overnight sleep on the same date wouldn't re-ask. Both
  are now anchored to a **sitting** (wake → sleep) instead: a session that crosses
  midnight is one sitting (asked once, no re-ask), and waking the machine after a
  night's sleep always starts a fresh sitting (always re-asks) regardless of the
  calendar date. A sitting ends on either an engine-detected suspend/hibernate gap (any
  length) or a continuous idle/away/locked span reaching a new `sitting_gap_hours`
  setting (default 4h) — short gaps like lunch never end it. Reading's midpoint is now
  anchored to the sitting's actual start rather than whenever the question happened to
  be answered. `day_plans` gains two nullable columns (`started_ts`, `ended_ts`,
  additive migration; table name kept for compatibility) and the storage API moves from
  one-row-per-date lookups to an open/close sitting model. Any sitting left open by a
  killed process gets closed on the next launch instead of lingering. 330 tests total
  (up from 313), including a new `tests/test_sitting.py` covering the 7 spec-mandated
  boundary scenarios (midnight crossing, overnight suspend, short gaps, threshold edge,
  zombie cleanup, reading-offer reset, migration).

### Added
- **Big Break activity menu + duration picker** — Big Break now shows all 5 curated presets
  (was only 3 of 5) plus a "Choose your own →" path: pick from 8 activities (Walk, Run,
  Bike, Sprint Intervals, Weightlifting, Gym Session, Jump Rope, KB Circuit), then a
  duration — 1-min steps to 30 min, 5-min steps to 2 h, 15-min steps to 4 h, or
  "Open-ended — stop when I'm done" (a stopwatch that logs actual elapsed time). Walk is
  intensity `"easy"` and never consumes the daily training cap, and stays offerable in the
  menu even once the cap is spent — hard activities grey out instead with a one-line reason.
  Hard-lock enforcement now only applies to Big Break sessions ≤ 90 minutes and not
  open-ended (`BIG_BREAK_HARDLOCK_CEILING_MIN`, see SETTINGS.md) — closes the multi-hour
  hard-lock footgun. `breaks` gains two nullable columns (`activity_type`, `activity_minutes`,
  additive migration) so completed sessions log which activity and how long, without touching
  existing insights (`layer` stays `"big"`). 25 new tests.
- **Reading sessions (day plan)** — at the first active moment of each day, PULSE asks
  "How long are you at the desk today?" (half-hour-step picker, skippable without guilt).
  If the planned day is 4+ hours (configurable), a 30-minute reading break (configurable)
  is scheduled at the midpoint of the window. When due, the corner widget offers it the
  same gentle way as training breaks; the next break becomes "grab your book" with a
  self-started timer. Recorded in a new `day_plans` table (included in data export) and
  the `breaks` log with layer `reading`. New "Reading" settings group with explainers.
- **Data export** — Settings → "Your data": export check-ins, breaks, meal answers,
  and daily active-time totals to CSV or JSON, all data or last 30/90 days. Local-only:
  you pick the folder via a native dialog, files are written there, nothing is sent
  anywhere. A `PULSE_EXPORT_README.txt` manifest rides along explaining every column
  and restating the privacy floor. Epoch timestamps get a human-readable `ts_iso`
  column so CSVs open cleanly in spreadsheets.
- **Meal detail chips** — after answering "Yes, I'm good" to the meal question, an
  optional follow-up collects food size (Light snack / Medium meal / Heavy meal) and
  water amount (A little / A glass / Plenty). Skippable; stored in new
  `food_detail` / `water_amount` columns via a safe additive migration.

### Fixed
- Corner widget "Do it" button on the training-ready card now works — it previously
  routed to an unwired callback and did nothing unless the countdown had taken over
  the card. Training and reading offers now route through the same break entry point.
- Countdown no longer ticks backward after idle periods — the widget now derives its
  display from a wall-clock deadline and ignores upward corrections from the
  active-time engine.
- Meal question buttons ("Yes, I'm good" / "Not yet") now work — author CSS
  (`display: flex` on cards) was overriding the browser's `[hidden]` handling; fixed
  with an explicit `[hidden] { display: none !important }` rule across all card CSS.
- PyInstaller launch crash (relative import in the entry module).

---

## [0.1.0] — Initial packaged release (all 13 build steps complete)

### Added
- Corner countdown widget (frameless, always-on-top, near the system clock).
- Light movement layer: configurable interval + advance warning, self-started break
  timer, movement suggestions, hydration on every break.
- Boundary/training layer: exercise pairs (6 categories × 3 levels with auto
  progression/deload), 12-minute Big Break alternative, daily cap, optional
  honest hard-lock.
- Progressive reflection: one-tap ratings → block type → notes, unlock meter with a
  15-observation evidence floor, "was this useful?" cadence every 5.5 active hours.
- Meal windows: "have you eaten today?" with duration picker for food breaks.
- Focus Guard: suppresses escalation during deep work; wave-off button.
- Weekly Insights view with pattern detection behind the evidence floor.
- Settings with three-part explainers (what / who it suits / trade-off) and
  5 preference profiles; guided first-run.
- System tray + optional per-user startup (HKCU, no admin).
- Optional PocketBase sync over Tailscale (off by default; token from env var only).
- Windows packaging: PyInstaller one-dir + Inno Setup, WebView2 runtime check.
- 262 unit tests with mocked-clock design.

---

*For full history, see the git commit log.*
