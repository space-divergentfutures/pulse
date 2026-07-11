# PULSE — Settings Reference

All settings live in SQLite (never in config.yaml — that's machine plumbing only).
Every setting has a plain-language **?** explainer in the app; this file is the
technical reference for contributors and advanced users.

Values are JSON-encoded in the `settings` table. Defaults are applied in code when
a key is absent — the database starts empty, so defaults cost nothing.

---

## Light breaks

| Key | Kind | Default | Range |
|-----|------|---------|-------|
| `enforcement_light` | choice | `corner_countdown` | `corner_countdown` · `soft_overlay` · `hard_lock` |
| `snooze_light` | choice | `off` | `off` · `one` · `multi` |
| `timing_mode` | choice | `dynamic` | `dynamic` · `fixed` |
| `warning_lead_minutes` | number | `5.0` | 0.5 – 15 min |
| `light_interval_minutes` | number | `30.0` | 10 – 90 min |
| `light_break_seconds` | number | `90.0` | 30 – 300 s |

**enforcement_light** — how a light movement break asks for attention.
- `corner_countdown` — quiet always-on-top countdown in the bottom-right corner; easy to ignore.
- `soft_overlay` — dismissible full-screen card; harder to scroll past.
- `hard_lock` — best-effort wall (full-screen overlay); technically escapable via Ctrl+Alt+Del
  and the explainer says so — PULSE offers accountability, not force.

**timing_mode** — whether breaks land on the app's fixed clock or wait for you to trigger them.
- `dynamic` — you click "Break now" at a natural stopping point; the countdown just shows when you're due.
- `fixed` — the break fires on the timer regardless of where you are in a thought.

**warning_lead_minutes** — how early the corner countdown appears before the break is due.

---

## Training breaks

| Key | Kind | Default | Range |
|-----|------|---------|-------|
| `enforcement_training` | choice | `session_card` | `session_card` · `soft_overlay` · `hard_lock` |
| `max_training_sessions_per_day` | number | `2.0` | 0 – 4 /day |
| `training_enabled` | bool | `true` | — |

**training_enabled** — whether the harder training layer (strength/conditioning exercises)
is offered at all. Off = light movement nudges only.

**max_training_sessions_per_day** — cap on **hard-intensity** sessions per day (regular
training sessions, and Big Break activities whose catalogue entry is `intensity: "hard"` —
Run, Bike, Sprint Intervals, Weightlifting, Gym Session, Jump Rope, KB Circuit). Walk is
`intensity: "easy"` and never consumes this cap — it stays offerable in the Big Break menu
even once the cap is spent for the day (see `pulse/data/big_break.json`).

**Big Break hard-lock ceiling** — `BIG_BREAK_HARDLOCK_CEILING_MIN = 90` (a module constant
in `pulse/training.py`, **not** a user setting). When `enforcement_training` is `hard_lock`,
a Big Break session is only hard-lockable if its duration is ≤ 90 minutes and it isn't
open-ended; anything longer, or the open-ended "stop when I'm done" stopwatch option, is
always honour-based regardless of the enforcement setting. This closes the obvious footgun
of a multi-hour (or unbounded) hard-locked session — hard-lock stays scoped to genuinely
short, bounded efforts.

---

## Reflection

| Key | Kind | Default | Values |
|-----|------|---------|--------|
| `tracking_enabled` | bool | `true` | — |
| `rating_scale_style` | choice | `numbers` | `numbers` · `faces` · `words` |

**tracking_enabled** — whether post-break ratings, the graph, unlock meter, and patterns are shown.
Off = movement-only mode; nothing is logged.

**rating_scale_style** — the format for the one-tap block rating.
- `numbers` — 1–10 slider (most granular).
- `faces` — 5 emoji faces (faster, coarser).
- `words` — 5 labelled words (fastest for people for whom numbers stop meaning things).

---

## Body floor

| Key | Kind | Default |
|-----|------|---------|
| `meal_windows_enabled` | bool | `true` |

**meal_windows_enabled** — whether the first break inside a meal window (default: lunch,
11:30–13:30) asks "have you eaten today?". Answering No offers a longer "go make a sandwich"
break. Once settled per window per day.

---

## Reading

| Key | Kind | Default | Range |
|-----|------|---------|-------|
| `reading_enabled` | bool | `true` | — |
| `reading_session_minutes` | number | `30.0` | 10 – 60 min |
| `reading_min_day_hours` | number | `4.0` | 1 – 10 hrs |
| `sitting_gap_hours` | number | `4.0` | 1 – 12 hrs |

**reading_enabled** — at the first active moment of each **sitting** (wake → sleep, not a
calendar date — see `sitting_gap_hours`), PULSE asks how long you're at the desk ("Start my
day" card, +/- picker in half-hour steps, skippable). If the planned sitting is at least
`reading_min_day_hours` long, a reading session is scheduled at the midpoint of the sitting.
When it's due, the corner widget shows "Reading break — whenever you're ready" (same gentle
offer pattern as training), and the next break you start becomes the reading break: grab
your book, self-started timer, hydration still rides. Honour-based; recorded in the `breaks`
table with layer `reading`. Off = no plan question, no reading offers; all other layers
unaffected.

**reading_session_minutes** — length of the reading timer.

**reading_min_day_hours** — planned sittings shorter than this stay purely work + movement.
(Key name is historical from the day-based version; kept for compatibility.)

**sitting_gap_hours** — a sitting is anchored to wake-and-sleep, not the calendar: it starts
at the first active moment after a qualifying gap and ends, backdated to your last active
moment, when the next qualifying gap begins. A gap qualifies when either (a) the engine
detects a suspend/hibernate-scale poll gap, at any length — closing the lid always ends a
sitting, or (b) you've been continuously idle/away/locked for at least `sitting_gap_hours`.
This is why a session crossing midnight is one sitting (no re-ask), while waking the machine
after a night's sleep always starts a fresh one (always re-asks) regardless of the date. A
lunch break or short errand, being well under the threshold, never re-asks. See
`pulse.dayplan.is_qualifying_gap` and `PulseApp._tick_sitting`.

---

## Appearance

| Key | Kind | Default | Values |
|-----|------|---------|--------|
| `appearance_theme` | choice | `dark` | `dark` · `light` · `dark_hc` · `light_hc` |
| `appearance_accent` | choice | `teal` | `teal` · `violet` · `coral` · `sky` · `sage` · `peach` · `lavender` |
| `appearance_font_size` | choice | `normal` | `small` · `normal` · `large` · `xlarge` |
| `appearance_font` | choice | `default` | `default` · `mono` · `serif` |

All colours are tested for readable contrast on both dark and light themes.
Font scaling uses the browser zoom mechanism — layout proportions stay consistent.

---

## System

| Key | Kind | Default |
|-----|------|---------|
| `start_with_windows` | bool | `false` |

**start_with_windows** — adds PULSE to the HKCU Run key so it launches automatically at login.
No administrator rights required. Only takes effect in the packaged app (not `python -m pulse`).

---

## Focus Guard

| Key | Kind | Default |
|-----|------|---------|
| `focus_mode_enabled` | bool | `false` |

**focus_mode_enabled** — while on, the light layer shows only the quiet corner countdown
(never escalates, never pulses). Training breaks wait until the current focus block ends
naturally. Body floor (hydration, meal window) still fires on any break that does land.

---

## Sync

| Key | Kind | Default |
|-----|------|---------|
| `sync_enabled` | bool | `false` |

**sync_enabled** — enables optional PocketBase sync over Tailscale (spec §12).
Requires `sync_url` in `config.yaml` and `PULSE_PB_TOKEN` in the environment — the token is
never stored in any file. Local SQLite is always the source of truth; sync is best-effort.

---

## Internal keys (not in SETTING_DEFS — managed by the app)

| Key | Kind | Purpose |
|-----|------|---------|
| `first_run_complete` | bool | Marks first-run wizard done; hides it on next launch |
| `active_profile` | string | Last applied profile key (e.g. `long_ramp`) |

---

## config.yaml (machine plumbing — NOT settings)

Stored at `%LOCALAPPDATA%\PULSE\config.yaml`. Not committed; not per-user preference.
See `config.example.yaml` for the full template.

| Key | Purpose |
|-----|---------|
| `db_path` | Override the SQLite path (default: `%LOCALAPPDATA%\PULSE\pulse.db`) |
| `sync_url` | PocketBase base URL, Tailnet only (e.g. `http://100.x.x.x:8090`) |
| `machine_name` | Optional friendly machine name |
