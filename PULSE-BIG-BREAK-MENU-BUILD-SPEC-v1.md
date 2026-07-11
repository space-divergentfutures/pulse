# PULSE — Big Break Activity Menu + Duration Picker
**Build Spec v1 — Claude Code handoff. Decisions locked; no open questions.**

*Supersedes the open questions in `PULSE-BIG-BREAK-ACTIVITY-MENU-DESIGN.md` (kept for the record). Origin: TJ voice note 2026-07-11 — the fixed 3-of-5 × 12-minute Big Break list is too narrow; he wants an activity menu (Weightlifting, Sprints, Run, Walk, Bike, Gym…) plus a scrollable duration picker up to multi-hour sessions.*

---

## 1. Locked decisions (the answers to the design doc's §Open Questions)

1. **Presets + pickers, not replacement.** The existing 5 curated options become one-tap **presets** that pre-fill activity + duration. A "Choose your own →" path opens the two new pickers. No regression: one tap still starts a 12-min session.
2. **Daily training cap — intensity-tagged.** Every activity type carries `intensity: "hard" | "easy"`. **Hard** sessions count against `max_training_sessions_per_day` (unchanged, default 2). **Easy** sessions (Walk) are logged but never consume the cap, and remain offerable when the cap is spent. Rationale: the cap is an overtraining guardrail on hard efforts; a walk is not a hard effort, and "you can always walk" is the right floor.
3. **Hard-lock ceiling.** Hard-lock enforcement applies to a Big Break only when the chosen duration is **≤ 90 minutes and not open-ended** (`BIG_BREAK_HARDLOCK_CEILING_MIN = 90`, module constant, documented in SETTINGS.md — not a user setting; don't grow the settings surface). Above the ceiling or open-ended → honour-based regardless of the training enforcement setting. A hard-locked multi-hour entry is a footgun; this closes it silently and predictably.
4. **Countdown AND stopwatch.** The duration picker is pick-then-countdown (extended range). The picker's top entry is **"Open-ended — stop when I'm done"**: starts an elapsed-time stopwatch; user taps **Done** on return; actual elapsed minutes are logged. Open-ended is never hard-locked (see 3).
5. **Cues stay.** Every activity type carries a one-line `cue` (warm-up/pacing line). Presets keep their full existing description + cue. A custom "Gym — 90 min" shows the Gym cue. This keeps the considered feel without per-duration coaching text.
6. **Storage — additive columns.** `breaks` gains two nullable columns: `activity_type TEXT`, `activity_minutes REAL` (actual minutes — for countdown sessions the chosen duration; for open-ended the measured elapsed). Additive migration in `storage.py`, exactly the `food_detail`/`water_amount` pattern already in `_migrate` (storage.py ~line 169). `layer` stays `"big"` so all existing insights keep working; the new columns enable future "you biked 3× this week" insights (do NOT build those insights in this pass).
7. **Walk vs light layer — deliberate, documented.** The §5a light layer stays what it is: 1–2 min honour-based movement snacks on the ~30-min clock. A Walk Big Break is a *chosen session at a block boundary* (20+ min, logged, duration-tracked). Different job, different clock. Add one sentence to README/spec noting this so it reads as intentional.

---

## 2. Data — `pulse/data/big_break.json` (new shape)

Replace the flat `options` list with `activities` + `presets`:

```json
{
  "activities": [
    { "id": "walk",       "name": "Walk",             "intensity": "easy", "rain_ok": false, "default_minutes": 20,
      "cue": "Just walk. Pace doesn't matter — being outside and moving does." },
    { "id": "run",        "name": "Run",              "intensity": "hard", "rain_ok": false, "default_minutes": 15,
      "cue": "Conversational pace unless you decided otherwise before you left. Warm into it — first 3 minutes easy." },
    { "id": "bike",       "name": "Bike",             "intensity": "hard", "rain_ok": true,  "default_minutes": 20,
      "cue": "Warm up 5 min easy before any hard pushes. Hard means legs burning; easy means actually easy." },
    { "id": "sprints",    "name": "Sprint Intervals", "intensity": "hard", "rain_ok": false, "default_minutes": 12,
      "cue": "2 min jog + leg swings first — sprints carry cold-start injury risk; the warm-up is not optional. 80–90%, never all-out." },
    { "id": "weights",    "name": "Weightlifting",    "intensity": "hard", "rain_ok": true,  "default_minutes": 45,
      "cue": "Warm-up sets first. Quality reps over load. Stop the set when form goes, not when ego does." },
    { "id": "gym",        "name": "Gym Session",      "intensity": "hard", "rain_ok": true,  "default_minutes": 60,
      "cue": "Have the first exercise decided before you walk in — the plan survives contact better than motivation does." },
    { "id": "jump_rope",  "name": "Jump Rope",        "intensity": "hard", "rain_ok": true,  "default_minutes": 12,
      "cue": "Stay light on your feet. Land on the toes, keep the bounce small." },
    { "id": "kb_circuit", "name": "KB Circuit",       "intensity": "hard", "rain_ok": true,  "default_minutes": 12,
      "cue": "Move with purpose, not urgency. Don't sacrifice the hinge for speed." }
  ],
  "presets": [
    { "id": "sprint_intervals", "activity": "sprints",    "name": "Sprint Intervals",  "duration_minutes": 12,
      "description": "2 min easy jog to warm up. Then 8 × 30 s sprint / 60 s walk. Cool down 1–2 min." },
    { "id": "easy_run",         "activity": "run",        "name": "12-min Run",        "duration_minutes": 12,
      "description": "Easy conversational pace for the full 12 min. No stops." },
    { "id": "bike_intervals",   "activity": "bike",       "name": "Bike — Hard Pushes","duration_minutes": 12,
      "description": "5 min easy warm-up, then alternate 30 s hard / 90 s easy for the remaining time." },
    { "id": "kb_amrap",         "activity": "kb_circuit", "name": "Outdoor KB Circuit","duration_minutes": 12,
      "description": "AMRAP 12 min: KB swings 15 / goblet squat 10 / pushups 10. Rest as needed." },
    { "id": "jump_rope",        "activity": "jump_rope",  "name": "Jump-Rope Intervals","duration_minutes": 12,
      "description": "40 s on / 20 s off for 12 min. Simple footwork — no tricks." }
  ]
}
```

Preset `id`s are unchanged from today's pool (stable identity for any existing logged data). Preset cue = its activity's cue; preset description shown as today.

---

## 3. UI flow — `pulse/ui/web/training_card.html/.css/.js`

```
get-ready screen → "Or, go outside/move →"
  → #phaseBigPick (UPDATED):
       • ALL presets shown (currently first-3-of-5 — fix), each with an
         "indoor OK" badge when rain_ok
       • one-tap preset → straight to timer (unchanged behaviour)
       • last card: "Choose your own →"
  → #phaseBigActivity (NEW): grid of the 8 activities (name + cue on focus/tap)
  → #phaseBigDuration (NEW): scrollable duration picker
       • top entry: "Open-ended — stop when I'm done"
       • then 1-min steps to 30 min → 5-min steps to 2 h → 15-min steps to 4 h
       • pre-selected at the activity's default_minutes
  → confirm → #phaseBigTimer:
       • countdown mode (as today) for picked durations
       • stopwatch mode (counts up + Done button) for open-ended
  → Done → completion path as today (+ new fields, §4)
```

Bridge methods for the two new phases go in `pulse/ui/training_card.py`, same pattern as the existing phase transitions.

---

## 4. Logic — `pulse/training.py`, `pulse/app.py`, `pulse/storage.py`

- `training.py`: load new schema; dataclasses `Activity(id, name, intensity, rain_ok, default_minutes, cue)` and preset loader replacing `pick_big_break_options` (return ALL presets; keep a thin compat shim only if the UI payload needs it). Duration-step helper for the picker lives here (pure function, unit-testable).
- `app.py` `_on_big_break_done(...)`: now receives `activity_id`, `elapsed_minutes`, `open_ended`. Cap consumption: only if the activity's intensity is `"hard"`. Hard-lock decision at session start: `hard_lock and not open_ended and minutes <= BIG_BREAK_HARDLOCK_CEILING_MIN`.
- `app.py` `_on_training_now`: when the daily cap is spent, easy activities remain offerable (the "you can always walk" path); hard presets/activities grey out with a one-line reason.
- `storage.py`: `_migrate` adds `activity_type`, `activity_minutes` to `breaks` (nullable, additive — copy the meal_prompts pattern at ~line 169); `record_break` gains the two optional params. Existing rows/insights untouched.

---

## 5. Tests (`tests/`)

1. Migration: old DB gains the two columns; existing rows intact.
2. Cap logic: hard consumes cap; easy never does; easy offerable at cap=spent; hard not.
3. Hard-lock ceiling: 90 min picked → lockable; 91 min → honour-based; open-ended → honour-based, always.
4. Duration-step helper: 1/5/15-min step boundaries correct; open-ended sentinel handled.
5. Open-ended completion logs measured elapsed minutes, not a preset duration.
6. Preset loader: all 5 presets returned, stable ids, activity linkage resolves.

---

## 6. Acceptance criteria

- One tap on a preset still starts a 12-min session — zero regression on the fast path.
- Custom path: any of 8 activities × any duration (1 min–4 h) or open-ended, with cue shown.
- A 3-hour Gym session cannot be hard-locked; a 12-min sprint session can (if enabled).
- Walking never consumes the training cap and is available even when the cap is spent.
- `breaks` rows carry activity + minutes for new sessions; old rows and all existing insights unaffected.
- SETTINGS.md documents the 90-min hard-lock ceiling; no new user-facing settings added.
- All existing tests pass; the 6 new test groups pass.

---

*Out of scope (explicitly): activity-based insights ("you biked 3× this week") — the columns make it possible later; do not build it now. No changes to the light layer, meal windows, or reflection engine.*
