# PULSE — Movement, Focus & Reflection Companion
**Build Specification v2.1 — Claude Code Handoff Document**

*A privacy-first, open-source desktop companion that nudges movement, protects deep focus, and builds gentle self-knowledge — designed for (but not limited to) ADHD and autistic minds.*

---

## 0. What changed from v2.0 (read this first)

v2.1 is the technical-review pass. The design philosophy is untouched; every change below either closes a gap, fixes something that wasn't buildable as written, or adds one feature (meal windows) that came out of the review conversation.

- **Hard-lock redefined honestly (§5b, §6):** a real "locked until done" screen is not implementable on Windows without malware-grade tricks. Hard-lock is now specced as a *best-effort wall* — a persistent fullscreen overlay that is technically escapable (Ctrl+Alt+Del) — and its explainer says so plainly. Design stance: PULSE offers accountability; it can't force it. An hour and one minute is better than nothing. Choose your own adventure.
- **NEW — Meal windows (§5d):** configurable meal windows (default: lunch, from 11:30). The first break inside a window asks "have you eaten today?" Yes → normal break. No → a longer break is offered with a duration picker ("go make a sandwich" mode). Once per window per day.
- **Hydration at every break (§5c, §5d):** hydration is not a separate nudge cadence — a hydration prompt rides on *every* break card. People on the spectrum often don't drink until their lips hurt; the fix is constant low-friction prompting, not another timer.
- **Insight engine gets statistical floors (§7):** no pattern is surfaced until it has ~15+ observations behind it, and all insights use hedged phrasing ("so far", "this week"). A mirror that shows fake patterns is worse than no mirror. The sleep-based example insight is cut (sleep isn't tracked).
- **NEW — First-run opening copy (§6):** external review (Grok, 2026-07-07) contributed the onboarding blurb that sets the app's contract on the very first screen — friction-tax framing, autonomy-first, lightly edited to avoid overclaiming ("shows you" not "learns") and deficit framing.
- **NEW — The unlock meter (§7):** the evidence floor is turned into the reward loop instead of a waiting room. From day 1 the user sees their data accumulating as unlabelled points, plus a visible progress % toward "unlocking" their first pattern — each check-in moves the bar. At 100% (= the floor is met) the labels and the first real insight reveal. The restriction *is* the game.
- **Weekly summary lives in PULSE itself (§7):** all references to an external "life app" removed. PULSE is standalone; export/integration is a later option.
- **Author's personal medical details removed (§10):** the public spec now carries generic safety principles only. Personal tuning lives in a private profile document, not in the open-source repo.
- **Platform abstraction expanded to five items (§3):** foreground-process check and fullscreen detection added alongside idle, lock, and startup.
- **Sleep/suspend + clock handling specced (§4):** big poll gaps (laptop lid closed, hibernate) are treated as AWAY; use `GetTickCount64` (the 32-bit tick counter wraps at ~49.7 days); session lock detected via `WTSRegisterSessionNotification`.
- **Sync conflict rules defined (§8):** every row carries a `machine_id`; primary keys are UUIDs; per-machine daily rows are summed, never overwritten. SQLite runs in WAL mode.
- **Distribution reality (§11):** one-dir PyInstaller build + Inno Setup installer instead of a single .exe (single-file builds trip antivirus/SmartScreen constantly for unsigned apps). README documents the SmartScreen warning. Installer checks for the WebView2 runtime and prompts if missing.
- **Big Break counts against the daily training cap (§5b, §9).**
- **Config precedence defined (§8):** `config.yaml` is machine plumbing only (DB path, sync URL); every user-facing setting lives in SQLite. No conflicts possible.
- **"5 consistent check-ins" defined (§7):** 5 non-skipped ratings across at least 3 distinct days.
- **Focus Mode is manual-only in v1 (§5c):** activity-based auto-detect can't distinguish deep work from frantic task-switching; it ships later, flagged experimental.
- **Unit tests from day one (§12):** the state machine and time accumulators get automated tests with a mocked clock as part of build step 1.
- **Startup via per-user registry Run key (§12):** simpler than Task Scheduler, no elevation needed.
- **Step 0 added to the build order (§12):** a spike proving the frameless always-on-top corner widget in pywebview *before anything else is built* — it's the highest-risk piece of the stack and the signature interaction. Fallback path documented.

### What changed from v1 (kept for history)

v1 was a single-user "force high-intensity exercise every 50 minutes and hard-lock the screen" tool. Research review (peer-reviewed evidence on movement breaks, exercise intensity and cognition, ADHD hyperfocus/task-switching cost, and autistic needs for predictability) reshaped the design: from one rigid interrupt to two gentle layers; from forced takeover to user-chosen timing; from surveillance to self-report; from hardcoded behaviour to fully configurable; from private tool to open-source app.

---

## 1. Core Philosophy — Tracker vs Mirror

**Every feature must serve reflection, not just data collection or compulsive accountability.**

This is the line that governs the whole app. A tracker ingests data and shows you numbers. A mirror shows you *yourself* — a causal pattern you couldn't see unaided ("your best-rated block today came right after you moved"). The failure mode we are explicitly designing against is the ADHD autopilot loop: rate 7, rate 7, rate 7, never asking what a 7 means anymore. Accountability without reflection is just another compulsion.

Three principles follow:

1. **The feedback is the point.** Data goes *in* one tap at a time; insight comes *back* visibly and immediately. For a dopamine-seeking brain, watching the graph respond to what you did is what makes the habit stick where willpower doesn't.
2. **Progressive disclosure is the therapeutic mechanism, not a UI nicety.** Introduce one thing to track, let the feedback loop become habit, and only then offer more. This mirrors how good self-monitoring is taught clinically — one variable at a time. Adding ten fields at once produces overwhelm-and-skip; adding one, then another five sessions later, produces reflection.
3. **The app offers structure; the person stays in control.** Predictable, advance-warned, opt-out-able, self-paced. It never diagnoses, never forces, never surveils.

> **North star:** if a feature makes the person *think about their own thinking* for a second, it belongs. If it just accumulates data or enforces compliance, it doesn't.

---

## 2. Who this is for (and the non-diagnostic stance)

Built for people whose executive function doesn't respond to passive notifications — prominently ADHD and autistic users — but useful to anyone who sits and works for long stretches.

**Explicitly non-diagnostic.** Lived experience of one's own neurotype is more fine-grained than any DSM label can produce. The app therefore never asks "do you have X" and never maps behaviour to a diagnosis. Instead it exposes well-explained **preference profiles** (§6) that a person self-selects and then freely tunes. Two people with the same diagnosis often want opposite settings; the app respects that by making everything a slider with an explainer, not a category with a prescription.

---

## 3. Architecture Overview

```
┌───────────────────────────────────────────────────────────┐
│  PULSE (Python 3.11+, single process)                     │
│                                                           │
│  ┌────────────────────┐   ┌────────────────────────────┐  │
│  │ Activity Presence  │   │ Session State Machine      │  │
│  │ (active-now check, │──▶│ work → warn → break → work │  │
│  │  STORES NOTHING)   │   │  + long-counter, hrs-counter│ │
│  └────────────────────┘   └──────────────┬─────────────┘  │
│                                          │                │
│  ┌────────────────────┐   ┌──────────────▼─────────────┐  │
│  │ Movement Scheduler │──▶│ UI Layer (pywebview)       │  │
│  │ (light + boundary  │   │  • corner countdown widget │  │
│  │  + meal windows)   │   │  • break card / overlay    │  │
│  └────────────────────┘   │  • check-in (1-tap rating) │  │
│                           │  • graph / insight view    │  │
│  ┌────────────────────┐   │  • settings + "?" explainers│ │
│  │ Reflection Engine  │──▶│                            │  │
│  │ (progressive stages)│  └──────────────┬─────────────┘  │
│  └────────────────────┘                  │                │
│                           ┌──────────────▼─────────────┐  │
│  ┌────────────────────┐   │ Storage: local SQLite (WAL)│  │
│  │ Platform Abstraction│  │  (source of truth, private)│  │
│  │ idle / lock / startup│ └──────────────┬─────────────┘  │
│  │ foreground / fullscr │                │                │
│  └────────────────────┘   ┌──────────────▼─────────────┐  │
│                           │ Optional Sync Module        │  │
│                           │ (PocketBase over Tailscale) │  │
│                           └────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
```

**v1 (this build) stack:**
- Python 3.11+
- Presence detection via `GetLastInputInfo` (Windows) behind a platform interface
- `pywebview` → all UI (corner widget, break card, check-in, graphs, settings) as HTML/CSS/JS
- `pystray` + `Pillow` → tray icon/menu (pystray runs in a background thread; pywebview owns the main thread)
- Local storage: **SQLite** (`pulse.db`, WAL mode) — richer queries than JSONL for the graphs/insights, still a single local file
- `requests`/`httpx` → optional PocketBase sync
- Config: `config.yaml` (machine plumbing only) + all user settings in SQLite (§8)
- Packaging: **PyInstaller one-dir build + Inno Setup installer** (§11)

**Known stack risk — spike first (Build Order step 0).** The signature corner widget needs a frameless, always-on-top window near the system clock. pywebview supports frameless and on-top; per-pixel transparency on Windows is unreliable. Step 0 proves this works before anything else is built. **Fallback if the spike fails:** a small native Win32 layered window for the corner widget only, with pywebview retained for break cards, check-ins, graphs, and settings. The widget doesn't need to be big — just visible enough to catch the eye where the clock already lives.

**Cross-platform readiness (build now, port later):** **five** things are OS-specific and MUST sit behind a clean `platform/` abstraction from day one — (1) idle/presence detection, (2) screen lock + lock-state detection, (3) startup registration, (4) foreground-process check (for defer conditions), (5) exclusive-fullscreen detection. Windows implementations now; macOS and Linux are later "write five adapters" jobs, not rewrites. Everything else (pywebview, pystray, SQLite) is already cross-platform.

> **Wayland caveat (record in README):** presence/idle detection is clean on Windows, macOS, and Linux/X11, but Wayland deliberately restricts idle-watching for security. Linux support will carry an asterisk until a Wayland-friendly path (e.g. `org.freedesktop.ScreenSaver` / logind idle hints) is implemented.

---

## 4. Presence Detection (privacy-first)

**Design rule: detect, don't record.** The app needs exactly one fact — *is the person active at the keyboard/mouse right now?* — to time breaks. It does **not** need, collect, or store window titles, app names, typed content, or keystroke streams. There is deliberately no surveillance surface to leak or be hacked.

Implementation:
- Poll `GetLastInputInfo` every 5 seconds → seconds since last input. This returns a single integer (idle time). No content, ever.
- **Use `GetTickCount64` for all tick arithmetic** — the 32-bit tick counter wraps at ~49.7 days of uptime and silently corrupts idle math.
- Derive presence state, accumulate **active time**, store only aggregate counters:
  - **ACTIVE**: last input < 60s ago → accumulate active seconds.
  - **IDLE**: ≥ 60s → pause accumulation, don't reset.
  - **AWAY**: ≥ `away_reset_minutes` (default 10) → the person took a real break; reset the short-break accumulator.
  - **LOCKED**: session lock → treat as AWAY. Detected via `WTSRegisterSessionNotification` (with a polling fallback), behind the platform interface.
- **Suspend/hibernate handling:** if the gap between two polls exceeds several poll intervals (default threshold: 60s), the machine was asleep — treat the gap as AWAY time, never as active time. No 2-hour laptop nap silently counted as work.
- What's persisted: accumulated active-minute totals, break events, and self-reported check-ins. Never a title, never a keystroke.

**Defer conditions** (so a break never lands mid-call/mid-recording): if a foreground process is on the `defer_processes` list (e.g. `zoom.exe`, `teams.exe`, `obs64.exe`) OR the foreground window is exclusive-fullscreen, defer and re-offer at the next interval. Detecting *that a meeting app is focused* is a process check, not content logging — no process names are ever stored, only the fact that a break was deferred. Both checks live in `platform/`.

---

## 5. The Break Model — Two Layers (+ the floor)

Two layers doing two different jobs on two different clocks. Neither is hardcoded; both are fully tunable (§6), and the labels below are just defaults.

### 5a. Light Movement Layer (frequent, gentle, self-triggered) — the default experience

**Job:** offset prolonged sitting; preserve cerebral blood flow and working memory (evidence: frequent short breaks beat one big workout for this). **Not** a training stimulus — light on purpose.

**Cadence:** every ~30 min of accumulated active time (`light_interval_minutes`, default 30).

**Interaction — this is the heart of the app:**
1. **Advance warning, not a jolt.** At `warning_lead_minutes` before the mark (default 5), a small **corner countdown widget** appears (bottom-right, near the clock — where the eye already goes; small, but sized to actually be readable) quietly counting down. No takeover. This solves the autism predictability need (you see it coming) and the ADHD flow need (you're not ambushed).
2. **You choose the moment.** The widget carries a **"Break now"** button. Finish the sentence/task you're on, then trigger the break yourself — even early. Landing the break at a natural stopping point is the entire design: completion satisfaction instead of an unfinished-loop tugging at you through the break.
3. **Dynamic, self-started timer.** When you hit "Break now" (or when the countdown hits 0 and you accept), a short **movement timer** starts — default 60–120s (`light_break_seconds`). *You* start it; it's not on the app's clock. Get up, move, come back.
4. **No snooze on this layer** (default) — there's nothing to snooze when you already control when it starts. The break card suggests a light movement (walk, mobility, band pull-aparts, a few squats) but rating/doing is honor-based.
5. **No hard-lock on this layer** (default) — it's a gentle nudge, not a wall. (Users who *want* a wall can enable it — §6.)

If the warning is ignored and the person keeps working well past the mark, the widget stays visible and gently escalates in prominence (configurable), but by default never seizes the screen.

### 5b. Boundary Training Layer (occasional, harder, at natural edges)

**Job:** real strength and conditioning for fitness/longevity — kettlebell work and a longer HIIT session. Evidence says hard intensity is for the body, not an acute cognitive boost, so it belongs at **work-block boundaries**, not slammed mid-thought.

**Cadence:** anchored to the deep-work rhythm (default: offered around every ~90 min of active work, or at a detected/declared block boundary), capped at `max_training_sessions_per_day` (default 2). **The Big Break counts against this cap** — it's a hard effort like any other. Two kettlebell sessions plus a HIIT is three hard efforts, and three hard efforts is the overtraining path the cap exists to block.

**Interaction:**
1. Same advance-warning courtesy: the corner widget signals a training break is coming up so it can be lined up with a natural stopping point.
2. On acceptance: a **get-ready window** (default 90s — lace up, grab the bell, warm up) then the session.
3. **Enforcement is the user's choice here** (§6). Default for a training session is a firmer commitment than the light layer — a full-screen session card with a timer — because the whole point is that the hard work doesn't get hand-waved. A **hard-lock option** is available for those who want the wall; it is **off by default** and honestly explained (below).
4. **Big Break variant** (12-min outdoor HIIT): a "choice" break — pick from 3 options (run / bike / sprints / KB circuit) so weather and energy decide.

**Hard-lock, defined honestly.** There is no legitimate way to hold a Windows machine hostage until a timer expires — the OS lock screen can simply be logged back into, and blocking Ctrl+Alt+Del is malware behaviour PULSE will never ship. So hard-lock means: a **persistent fullscreen overlay** that swallows the desktop and re-asserts itself (including re-appearing after an OS lock/unlock during a Big Break) until the session timer completes — *and it is technically escapable by anyone determined to escape it.* That's fine. PULSE is a commitment device, not a prison. The app offers as much accountability as software honestly can; if someone climbs the wall, they were never going to be locked in anyway. An hour and one minute is better than nothing.

### 5c. The Focus Guard (protecting deep work)

Deep synthesis work needs protected blocks (~90 min) and a 10–20 min ramp-up to full engagement — the reason 30-min chops are costly for complex work. So:

- A **Focus Mode toggle — manual in v1.** (Auto-detection from sustained activity is deferred: from raw input alone, deep writing and frantic tab-hopping look identical. It ships later, flagged experimental.) While active, the light layer softens to a purely passive corner nudge you can wave off, and the training layer defers to the *end* of the block.
- **The anti-crash floor:** even in Focus Mode, you cannot indefinitely skip. The hydration prompt still rides on every break that does land, meal windows (§5d) still fire, and the boundary break still arrives at the block's natural edge. You can defer *within* reason; you can't disappear into a 6-hour unbroken hyperfocus with no water and no food.

### 5d. Meal Windows & Hydration (the body's floor)

Hyperfocus makes people skip food and water until the crash. This isn't a tracking feature — it's two prompts riding on breaks that already exist. One interruption, never two.

**Hydration — every break, every layer.** Every break card carries a small hydration prompt ("water?" territory — one line, no logging, no guilt). People with spectrum wiring often don't drink until their lips hurt; the fix is constant low-friction prompting on a surface that's already in front of them, not another timer.

**Meal windows — configurable, default lunch.**
- The user defines meal windows (`meal_windows`, default: one window, "lunch", starting 11:30).
- The **first break of any kind that lands inside a window** adds one question to the break card: **"Have you eaten today?"** (question-mark/exclamation-point territory — a prompt, not a nag).
- **Yes** → normal break, question gone for the day (for that window).
- **No** → the break offers to grow: a duration picker (scroll-wheel style, e.g. 10–45 min) so there's actually time to go make a sandwich, plus a "save a lunch timer" option to schedule the meal break for slightly later if right-now doesn't work.
- Fires **once per window per day**, and only rides on a break that was happening anyway — because the person is already standing up, the activation cost of "go get food" is at its lowest.

---

## 6. Settings, Preference Profiles & "?" Explainers

**Nothing is hardcoded to one person's preference.** Every enforcement style ships as a setting. The author's own setup (corner countdown, no hard-lock, self-triggered timers) is just *one profile among several* — not the baked-in default for everyone.

### Configurable per layer
- **Enforcement style:** corner countdown (gentle) · soft full-screen overlay (dismissible) · hard-lock (persistent overlay until done — see §5b for what this honestly means)
- **Snooze:** off · one snooze · configurable snooze count + duration
- **Timing:** dynamic/self-triggered · fixed app-clock
- **Warning lead time**, **interval length**, **break duration**, **daily training cap**
- **Meal windows:** on/off, window times, duration-picker range
- **Rating scale style:** numbers (1–10) · faces · labelled words

### Preference profiles (tunable starting points, NOT diagnoses)
Presets that set sensible defaults across all the above, each fully editable afterward:
- **"Long ramp / protect focus"** — longer intervals, corner countdown only, Focus Guard aggressive, training deferred to boundaries.
- **"Frequent gentle nudges"** — shorter intervals, soft overlays, more reminders, low friction.
- **"High predictability"** — maximum advance warning, fixed timing, no surprises, consistent daily rhythm.
- **"Firm accountability"** — hard-lock enabled, snooze off, stricter completion requirements, for people who override softer prompts.
- **"Minimal / just movement"** — light layer only, no tracking, no training layer.

### "?" Explainers on every setting (required, not optional)
Without context people pick wrong — someone grabs "hard lock" thinking it means discipline, then bounces off the app when it shatters their focus; or skips "advance warning" not realising it's the thing that would've made transitions bearable. So **every setting has a "?" bubble** explaining three things in plain, non-clinical language:
1. **What it does**
2. **Who it tends to help** (framed as "this tends to suit people who…", never "pick this if you have X")
3. **The trade-off**

Example — hard-lock explainer (note the honesty about escapability; it's part of the design, not a disclaimer):
> *"Puts up a full-screen wall until the break is done. Tends to help people who override softer prompts and need a wall they can't argue with. Honest note: it's software, not handcuffs — a determined person can get past it, and that's okay; it works because you chose it, not because it's unbreakable. Trade-off: if you get deep into focus, being force-stopped can cost you the thread for a while — if that's you, try the corner countdown instead."*

### Guided first-run
First launch walks through the core choices **once**, with the explainers visible, and suggests a profile — a guided setup, not a wall of unexplained toggles. Everything is refinable later. The settings screen itself becomes partly self-teaching: reading the bubbles teaches a new user *why* the options exist and how their own patterns map onto them.

**First-run opening copy (canonical — external-review addition, 2026-07-07).** The very first screen, before any settings or data collection, sets the contract:

> **PULSE is built for people whose brains don't do well with constant low-grade friction.**
>
> Most reminder and tracking apps assume you just need a nudge. This one assumes something different: that the real cost isn't forgetting to move — it's the mental tax of *managing* the mundane stuff all day, every day. The decision fatigue, the context switching, the things that should be automatic but aren't.
>
> PULSE tries to take some of that load off your plate. It gives you advance warning before a break so you can finish your thought. It only interrupts when you choose. It shows you what actually helps *you* — built from your own ratings, not what some generic system thinks should help — and it only shows you patterns once there's enough real data to be honest about them.
>
> It was built by someone with the same wiring — tested on himself first, then with others who live it too. Nothing in here is prescriptive. Everything is configurable or driven by your own ratings. If a feature starts feeling like noise instead of support, you can turn it off or tell the app it's not useful.
>
> The goal is simple: give you back a bit more of your day and your energy for the things that actually matter to you — instead of getting slowly drained by the stuff your brain hates doing on autopilot.

Keep it short, honest, and autonomy-focused on screen; this is the source copy and may be trimmed for layout, never inflated.

---

## 7. Reflection Engine — Self-Report with Progressive Disclosure

The productivity/wellbeing signal comes from the **person, not the machine** — it's both privacy-preserving and higher-quality (a window title can't tell you whether the writing was any good or whether you were spiralling; you rating it can). The check-in rides on the break you're already taking — one interruption, not two.

### Progressive stages
Gated on **consistency and accumulated time**, never dumped all at once.

- **Stage 1 (from day 1):** exactly one question, one tap — **"How did that block go?"** on the user's chosen scale (default 1–10). Then **show the graph immediately** — this block vs recent ones, the shape of the day. That's the entire ask. The instant feedback is the reward.
- **Stage 2 (after 5 consistent check-ins — defined as 5 non-skipped ratings across at least 3 distinct days,** so five rapid taps in one afternoon don't count as a habit): the app *offers* **one** addition (not two) — e.g. **block-type** (deep work / admin / creative / meetings / scattered) *or* an **energy/feeling** rating (how you *feel*, distinct from how the work went — for many ND folks these diverge hard). User's choice, with a "?" explainer on why it might help.
- **Stage 3 (after that settles):** offer the optional **voice/text note** ("say more" — dictation or type: *"kept getting pulled to email," "breakthrough on the endgame lore," "foggy, bad night"*). This free-form note is the data that's genuinely *yours*. Begin surfacing the **first cross-patterns** (subject to the evidence floor below).

### Who controls the pace
The app **offers** on the consistency/time schedule, but an impatient (very ADHD) user can open settings and enable more whenever they want. **Staging is the default gentle path, not a cage** — it protects those who need protecting without locking out those who want to sprint. Users can also drop any dimension anytime.

### Every entry is skippable
A visible **skip** on every check-in. Skips are themselves logged quietly as a soft signal (a cluster of skips = maybe a rough stretch — information without nagging). No guilt UI.

### "Was this useful?" — the autopilot breaker
The key anti-compulsion mechanism. Periodically the app asks whether a tracked dimension is actually helping. This (a) keeps the app honest — drop dead metrics rather than accumulate them — and (b) forces a micro-moment of metacognition, the actual goal.

- **Cadence: every 5–6 accumulated *active hours*** (`useful_check_hours`, default 5.5), **not** per calendar day.
- **Why active-hours, not days:** it lands at a consistent amount of *lived experience* regardless of a 4-hour or a 10-hour day. Wall-clock "end of day" is the wrong anchor — you can't know in advance where it falls, and it misfires on short days / nags on long ones.
- **Self-limiting to ~once daily for free:** since most days stay under ~10 active hours, the 5.5-hour counter naturally yields one check-in most days, occasionally two on a genuinely long day where there's been enough *new* work to warrant asking again. That "not twice in a day" property falls out of the accumulator — no special rule needed.
- **The counter persists across days** (a 4-hour day carries remaining time into tomorrow); it does **not** reset at midnight.
- It targets whatever dimension is up for review (usually a recently-added one), not the whole tool — an occasional check-in on the new thing, then quiet.

### Insight surfacing — the payoff that makes it a mirror
Where the app earns its place: not showing a number, but a **causal pattern about the person** they'd never catch unaided.

**The evidence floor (non-negotiable).** An analyst doesn't call a crime trend off two incidents, and PULSE doesn't call a personal pattern off six ratings. In week one, any "pattern" in the data is almost certainly coincidence — and a mirror that shows fake patterns teaches the user to distrust the mirror, which kills the entire app. Therefore:

- **No pattern is surfaced until it has a minimum sample behind it** (`insight_min_observations`, default 15 relevant observations for the dimensions involved).
- **All insights use hedged, time-bounded phrasing** — "so far", "this week", "in the last 20 blocks" — never flat declarations of fact.
- **Correlation strength gates prominence:** weak signals appear as "worth watching" items, not headlines.

**The unlock meter — how the floor becomes the game.** A silent waiting period would kill retention for exactly the brains this app is for: an ADHD user who answers questions and gets nothing back doesn't come back. The floor must be *visible and gamified*, not hidden:

- **From day 1**, every check-in lands as a visible, unlabelled data point on the day/week view — colourful dots building on the graph. The user watches their data accumulate even before any pattern can honestly be called.
- **A progress meter counts toward the first insight unlock.** Each non-skipped check-in advances a visible percentage (calibrated to the evidence floor — e.g. 15 observations ≈ ~7% per entry). 8%… 16%… 24%… "quarter of the way"… the loop that makes people keep going is watching the bar move, and the bar is *honest* — it measures real progress toward statistical validity, not an arbitrary countdown.
- **At 100%, the reveal:** labels appear, the first genuine pattern unlocks, and the graph gains its interpretation layer. Subsequent insight types (new dimensions added at Stage 2/3) each get their own smaller unlock meters — there's always a next bar filling.
- **What unlocks is a pattern profile, never a placement.** The reveal is *"here are YOUR rhythms — your best hours, what movement does for your ratings, your energy shape"*. It is never a clinical or spectrum placement ("you're high on X") — that would violate the non-diagnostic stance (§2, §13) and would be false besides: block ratings measure how the work went, and cannot locate anyone on any clinical spectrum.

This is deliberate gamification of exactly one thing — progress toward honest insight — and nothing else. No points economy, no streaks, no badges (§13). The reward is the mirror itself.

Examples (post-floor, correctly phrased):
- *"So far, your sessions right after a movement break rate higher than the ones without — 12 of your last 15 best blocks followed movement."*
- *"This week, your best-rated blocks are mornings."*
- *"Three back-to-back deep sessions → your afternoon blocks dropped to 3s. A boundary break may help."*

Daily entry stays frictionless; **all the insight lives in a weekly summary view inside PULSE** (Insights tab). Patterns only emerge because entry was kept light enough to log consistently. (Export of the weekly summary, and integration hooks for other tools, are later options — PULSE stands alone.)

---

## 8. Data & Storage

### Local-first (default, zero-setup)
**SQLite (`pulse.db`, WAL mode), fully local, is the source of truth.** The app works completely offline with no accounts, no cloud, no server — essential for a public open-source tool where most users won't run any backend.

Core tables (illustrative):
- `active_time` — daily accumulated active minutes, **per machine** (`machine_id` column).
- `breaks` — UUID id, machine_id, timestamp, layer (light/training/big), enforcement used, accepted/deferred/skipped, duration.
- `checkins` — UUID id, machine_id, timestamp, block rating, optional block-type, optional energy rating, optional note, skipped flag.
- `meal_prompts` — UUID id, machine_id, date, window, answered (yes/no/skipped), extended-break duration if taken.
- `settings` — all user preferences and the active profile.
- `tracked_dimensions` — which reflection dimensions are enabled, when added, last "useful?" response.

**ID and merge rules (designed in now, free; painful to retrofit):** every row has a UUID primary key and a `machine_id`, so records from two machines can never collide or overwrite each other. Daily active-time totals are stored per-machine and **summed** at display time — never merged destructively.

**Config precedence:** `config.yaml` holds machine plumbing only — DB path, sync base URL, machine name. **Every user-facing setting lives in SQLite.** Two homes, zero overlap, no "which one wins" bugs.

Nothing in storage contains window titles, app names, or keystroke data.

### Optional Sync Module (off by default)
For multi-machine users, an **optional** module syncs to **PocketBase over Tailscale** — point both machines at one PocketBase instance so records meet there directly (Tailscale removes any need for a cloud middleman). Ships **disabled**; enabling it is a settings toggle + a base URL + a token in an env var (`PULSE_PB_TOKEN`, never hardcoded; Tailnet-only, never internet-exposed). Local SQLite remains source of truth; sync is best-effort with a retry queue, so a public user who never touches this loses nothing. The UUID + machine_id rules above are what make the merge trivially safe.

---

## 9. Exercise Content

### Equipment assumptions (all configurable)
Default kit: kettlebell, doorway pull-up bar, resistance bands, ~2×2 m floor. Users declare their own equipment; the library filters to what they have.

### Light layer pool (short, easy — movement snacks, not training)
Walk 1–2 min · band pull-aparts · couch stretch · cat-cow / thoracic rotations · dead hang 20–45s · easy hip/ankle/shoulder mobility flow · a light set of air squats. Enough to stand, move, and reset cerebral blood flow — deliberately not fatiguing, so returning to cognitive work isn't impaired.

### Boundary/training layer library (`exercises.json`, L1/L2/L3 progressions)
**Hinge/Power:** KB swings (15/25/35) · KB deadlifts (12/20/single-leg 8/side)
**Push:** pushups (10/20/feet-elevated 15) · KB overhead press (6/10/8 heavier per side)
**Squat/Legs:** bodyweight squats (20/35/jump 20) · goblet squats (10/18/25 slow)
**Weighted Mobility (back/hip insurance):** goblet-squat hold 60–90s · couch stretch 60s/side · KB halos (8/12 per dir) · deep lunge w/ rotation 6/side · light Jefferson curl (5 slow — gated behind 2 pain-free weeks)
**Pull/Hang:** dead hang (20/45/75s) · band pull-aparts 20 · doorway/band rows (12/20) · pull-ups (negatives/3/8)
**Core/Carry:** plank (40/75/weighted 60s) · KB suitcase carry 40 steps/side · dead bugs 10/side · KB front-rack march 30s/side

### Big Break pool (12-min outdoor HIIT, timed, `big_break.json`)
Road sprint intervals · 10–12 min run · 12 min bike (with hard pushes) · hill/stair sprints · outdoor KB AMRAP circuit (swings 15 / goblet 10 / pushups 10) · (rain option) jump-rope intervals 40s on/20s off. **Counts as one of the day's capped training sessions (§5b).**

### Progression engine
Per-exercise level (L1/L2/L3). Auto-progress: 6 clean completions at a level → offer "level up?" (one tap). Deload: 2 consecutive skips → drop a level, no shame messaging.

---

## 10. Health & Safety Principles

*(Generic by design — personal tuning belongs in a user's own profile, never in the public spec.)*

- **Progressive loading over max-effort ballistics.** The library biases toward controlled, gradual progression; higher-risk movements (heavy swings, Jefferson curls) gate behind pain-free weeks at lower levels.
- **Load guardrail:** frequent breaks do NOT mean frequent hard sessions. The light layer is deliberately easy; hard work is capped (default 2 training sessions/day, Big Break included). The evidence-based goal is *frequent light movement + 1–2 concentrated hard efforts*, not accumulated hard volume — the latter is an overtraining/injury path and, per the cognition research, can even blunt mental performance.
- **Sprint caution:** sprints carry the highest cold-start injury risk — the get-ready window before any Big Break should include a light jog and leg swings; the library biases new users' first two weeks toward run/bike/circuit before true sprints.
- **Pain vs fatigue:** if a movement produces pain (not muscle fatigue), a one-tap "pain" flag drops that exercise from rotation for 7 days and surfaces it in the weekly summary.
- **Hydration and food are floor-level features, not add-ons** (§5d) — because the target users are exactly the people who skip both.
- **General:** this is a wellbeing companion, not medical advice; the README states as much for public users, and the first-run flow says it once, plainly.

---

## 11. Open Source & Distribution

- **License: AGPL-3.0** (copyleft — downstream forks and hosted derivatives stay open). *Supersedes the earlier MIT choice, per the 2026-07-07 umbrella licensing pass; the LICENSE file already sits in this folder. Attribution line: "Divergent Futures / Humans in Space".*
- **GitHub:** public repo (`space-divergentfutures/pulse`). README covers the non-diagnostic stance, the privacy posture (no surveillance, local-first), the Wayland caveat, the SmartScreen note below, and a plain-language "what this is / isn't."
- **Packaging: PyInstaller one-dir build + Inno Setup installer.** Not a single-file .exe — one-file builds are flagged by antivirus and SmartScreen constantly because malware uses the same packing technique and open-source apps ship unsigned. The installer route dramatically reduces false alarms.
- **SmartScreen honesty (README + download page):** unsigned open-source apps trigger the blue "Windows protected your PC" screen. Document that it's expected and how to proceed (More info → Run anyway). Code-signing (paid certificate) is a later option if the project grows.
- **WebView2 runtime:** the UI depends on Microsoft's WebView2 (present on nearly all Win10/11 machines). The installer checks and offers the official bootstrapper if it's missing.
- **Distribution later:** a **GitHub Actions release workflow** that auto-builds Windows/macOS/Linux installers on each tagged version, so users and contributors get real downloads with no manual builds.
- **Contribution-friendly:** the five-item `platform/` abstraction and a documented settings schema make it straightforward for contributors to add OS adapters and new preference profiles.
- **Rollout plan:** (1) author dogfoods for 1–2 weeks — the key self-test is whether the graph + unlock meter actually pull *him* back daily; (2) small second ring of adult ADHD friends for honest feedback (low-risk cohort, no minors); (3) public GitHub release only after both rounds. Feedback from rings 1–2 feeds the profiles and explainers before strangers ever see them.

---

## 12. Build Order (suggested Claude Code session plan)

0. **Spike the corner widget (do this before ANYTHING else):** prove a frameless, always-on-top pywebview window can sit near the system clock, render a countdown, and take a button click. If transparency fails, prove the opaque-rounded-rectangle version. If pywebview can't do it acceptably, prove the native Win32 layered-window fallback. **The whole app rests on this interaction — do not build around an unproven foundation.**
1. **Presence + state machine:** `GetLastInputInfo` (via `GetTickCount64`) behind the `platform/` interface; active-time accumulator; short + long + hours counters; suspend-gap → AWAY; lock detection. Stores only aggregates. **Unit tests with a mocked clock for the state machine and every accumulator — timing bugs are silent for weeks otherwise.** Console-verify.
2. **Corner countdown widget (production version):** the bottom-right countdown + "Break now" button + dynamic self-started timer, built on whatever step 0 proved. This is the signature interaction — get it right first.
3. **Light layer:** interval logic, light-movement suggestion card, hydration line on the break card, honor-based completion, no lock/snooze by default.
4. **Reflection Stage 1:** one-tap block rating + immediate graph. SQLite schema (WAL, UUIDs, machine_id) for `checkins` and `active_time`.
5. **Settings + "?" explainers + profiles:** every enforcement style as a setting; the 5 profiles; explainer bubbles; guided first-run.
6. **Meal windows:** window config, the "have you eaten?" prompt on the first in-window break, duration picker, once-per-window logic.
7. **Boundary/training layer + Big Break:** get-ready window, session card, honest hard-lock overlay (optional, off by default), daily cap (Big Break included), `exercises.json` + `big_break.json`, progression engine.
8. **Focus Guard:** manual Focus Mode toggle, softening + deferral, anti-crash floor (hydration + meal windows persist).
9. **Reflection Stages 2–3 + "was this useful?":** progressive-disclosure offers, block-type/energy/note dimensions, the 5–6 active-hour useful-check counter (persistent across days), first cross-pattern insights **behind the evidence floor**.
10. **Weekly insight view + unlock meter:** the in-app Insights tab with hedged, floored pattern surfacing; the day-1 unlabelled dot view and the progress-to-unlock meter (the meter should actually ship earlier, with step 4, since it's part of the Stage 1 feedback loop — the reveal logic lands here).
11. **Tray + startup:** pystray in a background thread — pause/resume, "break now" manual trigger, today's count, quit; startup via per-user registry Run key (HKCU, no elevation).
12. **Optional PocketBase sync module:** off by default; collections mirroring the UUID/machine_id schema, retry queue, Tailscale base URL.
13. **Package + open-source polish:** PyInstaller one-dir + Inno Setup, WebView2 check, README (SmartScreen note, Wayland caveat, non-diagnostic stance), LICENSE (AGPL-3.0, already in folder), settings-schema docs; note the Actions release workflow as a follow-up.

**Milestone 1** = steps 0–4: gentle corner-countdown breaks you trigger yourself, one-tap ratings, and a graph building through the day. That alone is a usable, honest tool. Everything after is iteration.

---

## 13. Non-Goals (v1)

- **No surveillance.** No window-title logging, no keystroke logging, no screenshots — ever. Presence detection stores nothing but aggregates.
- **No diagnosis.** No mapping of behaviour to clinical categories; preference profiles only.
- **No forced high-intensity.** Hard work is capped and opt-in; the default experience is gentle.
- **No fake insights.** Nothing surfaces below the evidence floor; no flat declarations from thin data.
- **No unbreakable locks.** Hard-lock is a chosen wall, honestly described as escapable — never an OS-fighting prison.
- No mobile app / phone notifications (the desk is where the problem is).
- No video exercise demos (form cues + simple diagrams only).
- No calorie/food tracking (the meal prompt asks one question; it never logs what you ate).
- No gamified points economy (they decay fast for ADHD; the graph + insight loop is the mechanism).
- No mandatory cloud/accounts — local-first, sync strictly optional.

---

*End of spec. Opening prompt for Claude Code: "Build PULSE per this spec, starting with Build Order step 0 (the corner-widget spike), then step 1. This is an open-source, privacy-first, non-diagnostic wellbeing companion — the corner-countdown interaction, the honest-accountability stance, and the tracker-vs-mirror philosophy (§1) are the things that must not be compromised."*
