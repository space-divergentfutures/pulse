# PULSE — External Review Packet v1

*Self-contained briefing for an outside reviewer (no other documents needed). Full build spec exists separately (`pulse-build-spec-v2_1.md`); this is the readable overview. Review the design — the pinned decisions at the bottom are settled and not up for relitigating.*

---

## What PULSE is, in one paragraph

A free, open-source (AGPL-3.0) Windows desktop app that sits quietly in the corner of the screen and does three things: nudges you to move regularly, protects your deep-focus blocks instead of shattering them, and slowly builds a picture of your own work patterns from one-tap self-ratings. Designed for ADHD and autistic minds — people whose executive function ignores passive notifications — but useful to anyone who sits and works for long stretches. Privacy-absolute: no window titles, no keystrokes, no screenshots, no cloud, no account. Everything lives in a local database on your machine.

## The core philosophy: tracker vs mirror

A tracker collects data and shows you numbers. A mirror shows you *yourself* — patterns you couldn't see unaided ("your best-rated block today came right after you moved"). Every feature must serve reflection; anything that just accumulates data or enforces compliance gets cut. The explicit failure mode being designed against: the ADHD autopilot loop where you rate 7, rate 7, rate 7 and never think about what a 7 means.

## First-run explainer (from external review, folded into spec §6 with light edits)

**PULSE is built for people whose brains don't do well with constant low-grade friction.**

Most reminder and tracking apps assume you just need a nudge. This one assumes something different: that the real cost isn't forgetting to move — it's the mental tax of *managing* the mundane stuff all day, every day. The decision fatigue, the context switching, the things that should be automatic but aren't.

PULSE tries to take some of that load off your plate. It gives you advance warning before a break so you can finish your thought. It only interrupts when you choose. It shows you what actually helps *you* — built from your own ratings, not what some generic system thinks should help — and it only shows you patterns once there's enough real data to be honest about them.

It was built by someone with the same wiring — tested on himself first, then with others who live it too. Nothing in here is prescriptive. Everything is configurable or driven by your own ratings. If a feature starts feeling like noise instead of support, you can turn it off or tell the app it's not useful.

The goal is simple: give you back a bit more of your day and your energy for the things that actually matter to you — instead of getting slowly drained by the stuff your brain hates doing on autopilot.

## What using it looks like — a day in the life

**Morning.** You start working. PULSE watches exactly one thing: whether the keyboard/mouse is active. It stores no content — just "active minutes."

**~25 minutes in.** A small countdown widget appears bottom-right, near the system clock — visible but silent. It says a movement break is coming in 5 minutes, with a "Break now" button. You finish your paragraph, hit the button *yourself* when you reach a natural stopping point. This is the signature interaction: you're warned in advance (autism-friendly predictability) and you choose the moment (ADHD-friendly flow protection). No ambush, no takeover.

**The break.** A card suggests 1–2 minutes of light movement — walk, stretch, band pull-aparts. Every break card carries a one-line hydration prompt (target users don't drink until their lips hurt). If it's after 11:30 and this is the first break in the lunch window, one extra question: "Have you eaten today?" No → the break offers to grow, with a duration picker, so there's time to make a sandwich.

**Back at the desk.** One question: "How did that block go?" — one tap on a 1–10 scale, skippable, no guilt. Your rating lands instantly as a dot on a graph of your day, and a progress bar ticks up: **48% toward unlocking your first pattern.**

**~90 minutes / a natural boundary.** Occasionally (capped at 2/day) the widget offers a *training* break — real exercise, kettlebell or a 12-minute outdoor HIIT, from a library filtered to the user's equipment, with L1/L2/L3 progressions. Hard work lives at block boundaries, never mid-thought — evidence says intensity serves the body, not an acute cognitive boost.

**Deep-work days.** A manual Focus Mode softens everything to a passive corner nudge and defers training to the block's end — but hydration/meal prompts persist, so a 6-hour hyperfocus can't run bodiless.

**End of week.** The Insights tab shows honestly-hedged patterns: "So far, your sessions right after movement rate higher — 12 of your last 15 best blocks followed movement."

## The two retention mechanisms (the part most apps get wrong)

1. **Instant feedback.** Every rating immediately changes a visible graph. Data in, insight back — same moment.
2. **The unlock meter.** The app refuses to declare patterns from thin data (statistical floor: ~15 observations minimum — an analyst doesn't call a trend off two incidents). But a silent waiting period kills ADHD retention, so the floor is *gamified*: from day 1 the user watches unlabelled dots accumulate plus a visible % bar toward "unlocking" their first pattern. At 100%, the reveal — labels, interpretation, their first real insight. Each new tracked dimension gets its own smaller unlock bar. This is deliberately the only gamification in the app: no points, no streaks, no badges. The bar measures real progress toward statistical validity.

## Configurability — profiles, not prescriptions

Everything is a setting: enforcement style (gentle corner countdown / dismissible overlay / opt-in hard-lock "wall"), snooze, timing, intervals, meal windows, rating scale style. Five preset profiles ("Long ramp / protect focus", "Frequent gentle nudges", "High predictability", "Firm accountability", "Minimal / just movement") — starting points, never diagnoses. Every setting carries a "?" explainer: what it does, who it tends to suit, the trade-off. First run is a guided walkthrough, not a wall of toggles.

**Hard-lock honesty:** the optional "wall" is a persistent fullscreen overlay, honestly documented as escapable (it's software, not handcuffs; blocking Ctrl+Alt+Del is malware behaviour). PULSE is a commitment device, not a prison — an hour and one minute is better than nothing.

## Reflection grows in stages (progressive disclosure)

- **Stage 1 (day 1):** one question, one tap. That's all.
- **Stage 2 (after 5 non-skipped ratings across 3+ days):** app *offers* one addition — block-type or an energy/feeling rating.
- **Stage 3:** optional free-form voice/text note; first cross-patterns.
- **"Was this useful?"** every ~5.5 accumulated active hours, the app asks whether a tracked dimension is actually helping — drop dead metrics, force a micro-moment of metacognition. The anti-compulsion valve.

Impatient users can unlock everything early in settings; staging is the default path, not a cage.

## The build

**Stack:** Python 3.11+, single process. UI entirely HTML/CSS/JS inside `pywebview` windows; `pystray` tray icon; SQLite (WAL) local database; optional PocketBase-over-Tailscale sync for multi-machine users (off by default). Windows first; all OS-specific code (idle detection, lock, startup, foreground-process check, fullscreen check) behind a `platform/` abstraction so macOS/Linux are adapter jobs, not rewrites. Packaged as PyInstaller one-dir + Inno Setup installer (single-file .exe builds trip antivirus/SmartScreen).

**Presence detection = one integer.** Poll Windows' `GetLastInputInfo` every 5s → seconds since last input. Derive ACTIVE/IDLE/AWAY/LOCKED, accumulate active minutes, store only aggregates. Breaks defer automatically if Zoom/Teams/OBS is focused or something is fullscreen (a process check — nothing stored).

**Build order (13 steps, condensed):**
0. **Spike the corner widget first** — frameless always-on-top pywebview window near the clock. Highest-risk piece; nothing gets built on an unproven foundation. Native Win32 fallback documented.
1. Presence + state machine, unit-tested with a mocked clock.
2. Corner countdown widget (production).
3. Light movement layer + hydration line.
4. Stage-1 rating + instant graph + unlock meter.
5. Settings, explainers, profiles, guided first-run.
6. Meal windows.
7. Training layer + Big Break + progression engine.
8. Focus Guard.
9. Reflection Stages 2–3 + "was this useful?".
10. Weekly insights view + unlock reveal logic.
11. Tray + startup (per-user registry key).
12. Optional sync module.
13. Packaging + README + release polish.

**Milestone 1 = steps 0–4:** self-triggered gentle breaks, one-tap ratings, a graph and an unlock bar building through the day. Usable, honest tool on its own; everything after is iteration.

**Rollout:** author dogfoods 1–2 weeks (key test: does the feedback loop pull *him* back daily), then a small ring of adult ADHD friends, then public release.

## Pinned decisions (settled — not seeking review on these)

1. **Non-diagnostic, absolutely.** Never maps behaviour to clinical categories; the unlock reveal is a personal pattern profile ("your rhythms"), never a spectrum placement.
2. **Privacy-absolute.** No titles, keystrokes, screenshots, cloud, or accounts. Local SQLite is the source of truth.
3. **Self-triggered breaks + advance warning** is the signature interaction and is not negotiable.
4. **The evidence floor + unlock meter** — no patterns declared below ~15 observations; the wait is gamified, not hidden.
5. **Honest hard-lock** — opt-in, documented as escapable.
6. **Hard training capped at 2/day** (Big Break included) — overtraining guardrail.
7. **Stack as specced** (Python/pywebview/SQLite, open-source AGPL-3.0, Windows-first).

## What feedback IS wanted

- Holes in the day-in-the-life flow — moments a real ADHD/autistic user would bounce.
- The unlock-meter calibration: is ~15 entries (roughly 2–3 days of normal use) the right length for the first unlock, or too long/short for retention?
- The five preference profiles: missing archetypes?
- The meal-window and hydration mechanics: right-sized, or scope creep?
- Anything in the reflection staging that smells like it would produce autopilot compliance instead of actual reflection.
- Any risk we haven't seen (safety, retention, community/open-source dynamics).
