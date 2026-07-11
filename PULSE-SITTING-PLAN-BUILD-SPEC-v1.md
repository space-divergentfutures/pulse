# PULSE — Day Plan → Sitting Plan (sleep-aware sessions)
**Build Spec v1 — Claude Code handoff. Decisions locked; no open questions.**

*Origin: TJ, 2026-07-11. Bug: the day-plan question ("how long are you at the desk?") is anchored to calendar midnight, so a late session crossing 12am consumed the next morning's question (real occurrence: answered "2 hours" at 12:05am, silent at the actual start of the day). Design drift: PULSE's own spec (§7) anchors cadences to lived time, not wall-clock — the day-plan feature violated that. Fix: anchor the question to a **sitting** (wake → sleep), not a date.*

---

## 1. The sitting model (locked)

1. **A sitting starts** at the first ACTIVE tick after a qualifying gap. A qualifying gap is any of:
   - system resume from suspend/hibernate (the presence layer's existing suspend-gap detection),
   - session unlock, away, or idle where the continuous non-ACTIVE span ≥ `sitting_gap_hours` (new setting, default 4.0),
   - app cold start when no sitting is open.
2. **The plan question fires once per sitting**, at the sitting's first active moment (same busy-guards as today: not during break/training/paused). Card copy changes from day-framing to sitting-framing: **"How long are you at the desk?"** (the card already asks essentially this; adjust any "today" wording in `dayplan.html`/strings).
3. **A sitting ends** when a qualifying gap begins — end time is backdated to the *last active moment*, not the moment the gap was recognised. Sleep/lock at 11pm → sitting ends 11pm, even though the 4-hour rule is only satisfied at 3am.
4. **Short gaps do nothing.** Lunch, errands, the machine napping for 40 minutes — same sitting continues, no re-ask. The threshold exists precisely so the question is never noise.
5. **Midnight is meaningless.** A sitting spanning 11pm–2am is one sitting. The next wake asks fresh.
6. **Reading is unchanged in behaviour, re-anchored in wording:** scheduled at the midpoint of the *sitting's* planned hours when planned ≥ `reading_min_day_hours` (keep the setting key for compat; update its label/explainer text from "day" to "sitting"). `reading_due` logic untouched. A reading offer never survives into the next sitting (reset on sitting end).

---

## 2. Settings

- **NEW `sitting_gap_hours`** — number, default 4.0, min 1.0, max 12.0, group "Reading" (or a new "Sessions" group if cleaner in the UI).
  - Explainer — what: "How long PULSE waits after you leave (or the machine sleeps) before treating your return as a fresh sitting — which asks the desk-time question again and re-anchors reading."
  - who: "Lower suits people with distinct morning/evening shifts at the desk; higher suits people who drift in and out all day and only want to be asked once."
  - tradeoff: "Too low re-asks after a long lunch; too high merges a morning and an evening session into one sitting."
- Update `reading_enabled` / `reading_min_day_hours` explainer text from day-language to sitting-language. Keys unchanged.

---

## 3. Storage (additive only — the meal_prompts migration pattern)

Keep the `day_plans` table (name is now historical; do NOT rename — compat with export and existing rows). Additive migration:

- `started_ts REAL` — sitting start (first active moment). Backfill NULL for old rows.
- `ended_ts REAL` — sitting end (last active moment before the qualifying gap). NULL while open / for old rows.
- Drop the one-row-per-date assumption in *queries only* (schema never enforced it): `day_plan_today()` is replaced by `open_sitting()` (most recent row with `ended_ts IS NULL` for this machine) + `close_sitting(id, ended_ts)`. `date` column stays populated (sitting start's local date) for export/insight grouping.
- On app start: any row left open from a previous run whose age exceeds the gap threshold gets closed at its last-known active moment (use the engine's last-active timestamp if available, else `ts`) — no zombie sittings.
- `export.py`: include the new columns; update the `day_plans` doc line ("one row per sitting you were asked about").

---

## 4. App logic (`pulse/app.py`, `pulse/dayplan.py`)

- `_tick_day_plan` → `_tick_sitting`: replace the `date.today()` comparison with sitting state:
  - Track `self._sitting_open` / `self._sitting_row_id` / last-active timestamp.
  - Qualifying-gap detection consumes what the presence layer already knows (AWAY spans, suspend gaps, lock state) — do not build a second detector; expose a helper from the engine if one isn't public.
  - On qualifying gap: close the open sitting (backdated end), clear reading-pending state.
  - On first active tick with no open sitting: open one, fire the ask (existing busy-guards).
- `_on_day_planned`: records against the open sitting row (planned_hours may be None on skip — unchanged).
- **Skip still means "don't ask again this sitting"** — a skipped sitting keeps its row (planned NULL) and stays open until it ends naturally.

---

## 5. Tests

1. Midnight crossing: active 23:00–01:30, no gap → ONE sitting, ONE ask, no re-ask after midnight.
2. Suspend overnight: active till 23:00, machine sleeps, wake 08:00 → sitting closed with `ended_ts` ≈ 23:00; new sitting at 08:00 asks again.
3. Short gap: 40-min AWAY → same sitting, no re-ask.
4. Threshold edge: gap of exactly `sitting_gap_hours` → new sitting; just under → same sitting.
5. Zombie cleanup: app killed with sitting open, restarted 6h later → old row closed, new sitting opens and asks.
6. Reading: pending reading offer does not survive sitting end; midpoint computed from sitting start.
7. Migration: old day_plans rows intact, new columns NULL, export includes them.

---

## 6. Acceptance criteria

- A session crossing midnight never re-asks and never eats the next morning's question.
- Waking the machine after a night's sleep always asks (if reading_enabled), regardless of calendar date.
- A lunch break never re-asks.
- Sittings are logged with start/end; export shows them; old data untouched.
- No new detectors — sitting boundaries derive from the existing presence/suspend/lock machinery.
- All existing tests pass + the 7 groups above.

*Out of scope: sitting-based insights ("your best blocks come from morning sittings") — the logged data enables it later; do not build now. No changes to breaks, training, meal windows, or the unlock meter.*
