# PULSE — Big Break activity menu + duration picker (Cowork design doc)

**Status:** Not yet a build spec — this is for Cowork to think through with TJ before it goes
to Claude Code. Current behaviour and code locations are included so Cowork doesn't have to
re-derive them from the repo.

**Source:** TJ, voice note, 2026-07-11 — "when a Big Break comes up, it says there's sprint
intervals, twelve minute run, bike hard pushes or indoors... we need to have another menu, and
multiple options within that — weightlifting, sprint intervals, run, walk, bike, gym — and
beside that, time intervals, a rolling tracker of one minute, two minute, three minute, up to
however many hours it happens to be... gives optionality outside of sprint intervals, 12-minute
run, and bike."

---

## What exists today

Big Break is the "go outside" alternative offered alongside a regular training session (spec
§5b). Currently:

- A **fixed pool of 5 options** in [`pulse/data/big_break.json`](pulse/data/big_break.json):
  Sprint Intervals, 12-min Run, Bike — Hard Pushes, Outdoor KB Circuit, Jump-Rope Intervals.
- Every option is **hardcoded to 12 minutes** (`duration_minutes: 12` per entry).
- Each option carries a `description`, a `cue`, and a `rain_ok` flag (indoor-safe or not).
- [`pick_big_break_options(n=3)`](pulse/training.py:124) returns the **first 3 of the 5** —
  not randomised, not filtered by weather/rain, always the same 3 in the same order.
- The picker UI is [`#phaseBigPick`](pulse/ui/web/training_card.html:56) — a flat list of
  cards, one per option, no categories.
- Once picked, [`#phaseBigTimer`](pulse/ui/web/training_card.html:61) runs a fixed countdown
  to the option's `duration_s` and shows its description/cue throughout.
- Completing a Big Break calls `_on_big_break_done` in [`app.py`](pulse/app.py:488) →
  `storage.record_break("big", enforcement, "completed")` → counts toward the same
  `max_training_sessions_per_day` cap as a regular training session (default 2/day).
- Big Break is reachable from the training get-ready screen ("Or, go outside for 12 min →")
  and is offered alongside a regular strength session — see `_on_training_now` in
  [`app.py`](pulse/app.py:440).

**The limitation TJ is hitting:** the activity list is short, every activity is nailed to
exactly 12 minutes, and there's no way to say "I biked for 45 minutes" or "I want a 2-hour
gym session" — the only knob is which of 3 fixed 12-minute options to pick.

---

## What TJ wants

Two separate pickers, chosen together before the timer starts:

1. **Activity type** — a proper menu, not just the current 5 hardcoded cards. Named
   examples: Weightlifting, Sprint intervals, Run, Walk, Bike, Gym. (Existing options like
   Jump-Rope and Outdoor KB Circuit presumably fold into this list too — see open questions.)
2. **Duration** — described as "a rolling tracker of one minute, two minute, three minute...
   up to twelve hours or twenty-four hours, whatever it happens to be." Read as: a scrollable
   duration picker, not fixed presets — free choice of length, with a wide practical range
   (minutes for a quick sprint session, hours for a gym block or a hike).

The goal stated directly: **optionality** — the current 3-of-5 fixed 12-minute list is too
narrow for how varied his actual movement sessions are.

---

## Open questions for Cowork + TJ to resolve before this becomes a build spec

These matter because the current Big Break is wired into the daily training cap, hard-lock
enforcement, and the reflection/insights layer — a free-form duration picker interacts with
all three in ways the fixed-12-min version never had to.

1. **Does this replace the curated list, or sit alongside it?**
   Keep "Sprint Intervals / 12-min Run / Bike Hard Pushes" as a quick-pick shortcut, with
   "choose your own" as a second path? Or fully replace the pool with activity-type +
   duration for everything?

2. **What happens to the daily training cap at long durations?**
   `max_training_sessions_per_day` (default 2) assumes each session is a short break. A
   4-hour "Gym" session completed at 9am would leave the cap saying only 1 more training
   break is available for the rest of the day — is that correct, or should long sessions
   (say, over some threshold) not count against the cap at all?

3. **What happens to hard-lock enforcement at long durations?**
   Training's `hard_lock` mode currently holds a full-screen wall until the session timer
   completes. A hard-locked 24-hour entry would be a serious footgun. Likely answer: cap
   hard-lock's applicability to Big Break at some sane ceiling (e.g. 60–90 min), or simply
   exclude Big Break from hard-lock entirely and make it always honour-based, regardless of
   the training enforcement setting. Needs a decision either way, not a silent default.

4. **Does "rolling tracker" mean a live elapsed-time count (I start now, stop whenever), or
   a duration you set before starting and then a countdown runs?**
   The quote reads like a picker UI (scroll to select 1 min / 2 min / 3 min / ... up to
   12–24 hrs) rather than a stopwatch — but for anything over ~2 hours, a pre-set countdown
   makes less sense than "I'm heading out, log it as done when I'm back." Worth confirming
   directly: pick-then-countdown (current model, extended range) vs. start-then-stop
   (stopwatch, log actual elapsed time on completion).

5. **Should custom activities carry a cue/description like the curated ones do**, or is a
   plain "Gym — 90 min" entry enough with no coaching text? The curated pool's cue text
   (warm-up reminders, pacing guidance) is part of what makes it feel considered rather than
   just a timer.

6. **Storage/reflection implications** — do these get logged with `layer = "big"` same as
   today (so they keep counting in existing insights), or does the activity type deserve its
   own column (`activity_type`, `activity_minutes`) so Insights can eventually show "you
   biked 3× this week" instead of just an undifferentiated Big Break count? Given PULSE
   already added `food_detail`/`water_amount` to `meal_prompts` for exactly this kind of
   richer-than-boolean answer, the same pattern (extra nullable columns, additive migration)
   would fit — Cowork should confirm scope, not just architecture.

7. **Where does "Walk" sit relative to the existing light-movement layer?**
   PULSE already has short honour-based movement suggestions every ~30 min (§5a). A 20-minute
   "Walk" Big Break and a 90-second "walk it out" light break are different enough in kind
   that they probably don't collide, but worth naming explicitly so the two don't end up
   feeling redundant.

---

## A strawman shape (for Cowork to react to, not a final spec)

```
Big Break flow:
  get-ready screen → "Or, go outside/move →"
    → ACTIVITY PICKER (grid or list: Weightlifting / Sprint intervals / Run / Walk / Bike / Gym / ...)
    → DURATION PICKER (scrollable, 1 min steps, sensible range e.g. 1 min – 4 hrs,
                        with a coarser step above some threshold — nobody needs 1-min
                        granularity at the 3-hour mark)
    → confirm → countdown/timer screen, same shape as today's #phaseBigTimer
    → Done → same completion path as today (record_break, training cap, check-in)
```

Existing curated options (Sprint Intervals, 12-min Run, etc.) could become **presets** that
pre-fill both pickers — fastest path stays one tap, but the pickers underneath are now real
menus instead of the only choice.

---

## Files a future build will likely touch

(For orientation only — do not start building from this list; wait for the resolved spec.)

- `pulse/data/big_break.json` — activity catalogue instead of/alongside the flat option list
- `pulse/training.py` — `pick_big_break_options` → activity list + duration range helpers
- `pulse/ui/web/training_card.html/.css/.js` — new picker phases (activity grid, duration
  scroll picker) between get-ready and the timer
- `pulse/ui/training_card.py` — bridge methods for the new picker steps
- `pulse/app.py` — `_on_training_now`, `_on_big_break_done`, and the training-cap /
  hard-lock interaction resolved in the open questions above
- `pulse/storage.py` — possible `breaks` table columns for activity type + a migration,
  mirroring the `food_detail`/`water_amount` precedent in `meal_prompts`
- `SETTINGS.md` / settings catalogue — if a duration ceiling or hard-lock exclusion becomes
  a user-facing setting rather than a hardcoded rule

---

## What this doc is not

Not a decision record — nothing above is locked in. It exists so Cowork has the real current
behaviour (not a guess) plus TJ's exact request, and can work through the open questions with
him before anything comes back to Claude Code as a numbered build spec.
