# PULSE Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
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
