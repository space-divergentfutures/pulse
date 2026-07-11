"""Training session builder and progression engine helpers (spec §5b, §9).

Loads the exercise library and Big Break pool from data files, picks sessions,
and wraps the progression storage in clean domain language.

Progression rules (spec §9):
  - Per-exercise level: L1 → L2 → L3.
  - Auto-level-up: 6 consecutive clean completions → promote one level.
  - Auto-deload:   2 consecutive skips → drop one level (no shame messaging).

Pain flag: drops an exercise from consideration for 7 days and surfaces it in
the weekly summary (step 10). The storage layer owns the date arithmetic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"
EXERCISES_FILE = _DATA_DIR / "exercises.json"
BIG_BREAK_FILE = _DATA_DIR / "big_break.json"


# ---------------------------------------------------------------------------
# Domain dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExerciseSpec:
    """One exercise as it will be shown in the training card."""
    id: str
    name: str
    work: str           # "25 reps" or "45s"
    cue: str
    level: int          # 1, 2, or 3
    duration_s: float | None  # None = reps-based; number = timed (plank, dead hang, etc.)
    equipment: tuple[str, ...]


@dataclass(frozen=True)
class TrainingSession:
    exercises: tuple[ExerciseSpec, ...]


@dataclass(frozen=True)
class Activity:
    """One Big Break activity type (spec: Big Break Activity Menu v1, §2).

    ``intensity`` drives the daily-cap and hard-lock rules: "easy" activities
    (Walk) never consume the training cap and stay offerable even once it's
    spent; "hard" activities behave like today's Big Break did."""
    id: str
    name: str
    intensity: str  # "hard" | "easy"
    rain_ok: bool
    default_minutes: float
    cue: str


@dataclass(frozen=True)
class BigBreakPreset:
    """A one-tap Big Break shortcut — an activity pre-filled with a duration and
    a fuller description. Cue/rain_ok/intensity are resolved from the activity."""
    id: str
    activity_id: str
    name: str
    duration_minutes: float
    description: str
    cue: str
    rain_ok: bool
    intensity: str


# The daily training cap is an overtraining guardrail on HARD effort only; a Big
# Break above this length, or an open-ended one, is never hard-locked regardless
# of the training enforcement setting — closes the multi-hour hard-lock footgun.
# Not a user setting (documented in SETTINGS.md, not exposed in the catalogue).
BIG_BREAK_HARDLOCK_CEILING_MIN = 90.0


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_exercises() -> dict:
    with EXERCISES_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def load_big_breaks() -> dict:
    """Raw parsed `big_break.json`: {"activities": [...], "presets": [...]}."""
    with BIG_BREAK_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def load_activities() -> list[Activity]:
    data = load_big_breaks()
    return [
        Activity(
            id=a["id"],
            name=a["name"],
            intensity=a["intensity"],
            rain_ok=a["rain_ok"],
            default_minutes=float(a["default_minutes"]),
            cue=a["cue"],
        )
        for a in data["activities"]
    ]


def _activities_by_id() -> dict[str, Activity]:
    return {a.id: a for a in load_activities()}


def activity_intensity(activity_id: str) -> str | None:
    """Intensity ("hard"/"easy") for an activity id, or None if unrecognised."""
    act = _activities_by_id().get(activity_id)
    return act.intensity if act is not None else None


def load_big_break_presets() -> list[BigBreakPreset]:
    """All Big Break presets, each resolved against its activity's cue/rain_ok/
    intensity. Presets carry stable ids so any historical logged data keeps
    matching by id across this schema change."""
    data = load_big_breaks()
    activities = _activities_by_id()
    presets = []
    for p in data["presets"]:
        act = activities[p["activity"]]
        presets.append(
            BigBreakPreset(
                id=p["id"],
                activity_id=p["activity"],
                name=p["name"],
                duration_minutes=float(p["duration_minutes"]),
                description=p["description"],
                cue=act.cue,
                rain_ok=act.rain_ok,
                intensity=act.intensity,
            )
        )
    return presets


# ---------------------------------------------------------------------------
# Session picking
# ---------------------------------------------------------------------------

def _parse_work(level_spec: dict) -> tuple[str, float | None]:
    """Return (work_label, duration_s). Timed exercises have a 'duration' key."""
    if "duration" in level_spec:
        dur_str = level_spec["duration"]  # e.g. "45s"
        try:
            duration_s = float(dur_str.rstrip("s"))
        except ValueError:
            duration_s = None
        return dur_str, duration_s
    return level_spec.get("reps", ""), None


def _make_spec(ex: dict, level: int) -> ExerciseSpec:
    level_spec = ex["levels"][max(0, min(level - 1, len(ex["levels"]) - 1))]
    work, duration_s = _parse_work(level_spec)
    return ExerciseSpec(
        id=ex["id"],
        name=ex["name"],
        work=work,
        cue=level_spec.get("cue", ""),
        level=level,
        duration_s=duration_s,
        equipment=tuple(ex.get("equipment", [])),
    )


def pick_session(storage, session_cursor: int = 0) -> TrainingSession:
    """Return a 2-exercise session by rotating through the 5 category pairs.

    Cursor increments after every completed session so the user cycles through
    all movement patterns. Pain-flagged exercises are not yet filtered here
    (step 10 will add rotation-aware exclusion).
    """
    data = load_exercises()
    cats = data["categories"]
    n = len(cats)
    # Two categories per session, spread across the library
    cat_a = cats[session_cursor % n]
    cat_b = cats[(session_cursor + 2) % n]

    def pick(cat: dict, cursor: int) -> ExerciseSpec:
        exs = cat["exercises"]
        ex = exs[cursor % len(exs)]
        level = storage.exercise_level(ex["id"])
        return _make_spec(ex, level)

    return TrainingSession(exercises=(pick(cat_a, session_cursor), pick(cat_b, session_cursor)))


# --- Big Break offerability + duration picker (pure, unit-testable) --------


def is_available(intensity: str, cap_spent: bool) -> bool:
    """Whether a Big Break item of this intensity can be offered right now.
    Easy activities (Walk) are always offerable — "you can always walk" is the
    floor under the daily hard-effort cap, not something the cap can remove."""
    return intensity == "easy" or not cap_spent


def big_break_is_hardlockable(minutes: float | None, open_ended: bool) -> bool:
    """Whether a Big Break of this length is eligible for hard-lock enforcement.
    Open-ended sessions and anything past the ceiling are always honour-based,
    regardless of the training enforcement setting."""
    if open_ended or minutes is None:
        return False
    return minutes <= BIG_BREAK_HARDLOCK_CEILING_MIN


def _format_minutes(m: int) -> str:
    if m < 60:
        return f"{m} min"
    hours, rem = divmod(m, 60)
    if rem == 0:
        return f"{hours} hr" if hours == 1 else f"{hours} hrs"
    return f"{hours}h {rem}m"


def duration_picker_options() -> list[dict]:
    """Ordered choices for the Big Break duration picker: an open-ended sentinel
    first (``minutes: None``), then 1-min steps to 30 min, 5-min steps to 2 h,
    15-min steps to 4 h. Each entry is JSON-shaped: {"minutes": ..., "label": ...}."""
    opts: list[dict] = [
        {"minutes": None, "label": "Open-ended — stop when I'm done"}
    ]
    for m in range(1, 31):
        opts.append({"minutes": float(m), "label": _format_minutes(m)})
    for m in range(35, 121, 5):
        opts.append({"minutes": float(m), "label": _format_minutes(m)})
    for m in range(135, 241, 15):
        opts.append({"minutes": float(m), "label": _format_minutes(m)})
    return opts


# ---------------------------------------------------------------------------
# Session payload (JSON-serialisable, passed to the JS training card)
# ---------------------------------------------------------------------------

def session_payload(session: TrainingSession, hard_lock: bool = False) -> dict:
    return {
        "type": "training",
        "hardLock": hard_lock,
        "exercises": [
            {
                "id": e.id,
                "name": e.name,
                "work": e.work,
                "cue": e.cue,
                "level": e.level,
                "duration_s": e.duration_s,
            }
            for e in session.exercises
        ],
    }


def big_break_payload(cap_spent: bool, hard_lock_enabled: bool) -> dict:
    """Everything the training card needs for the Big Break flow: all presets,
    the full activity catalogue, and the duration-picker choices. Items whose
    intensity is "hard" are marked unavailable once the daily cap is spent;
    "easy" items (Walk) are always available. Presets carry a precomputed
    hardLock flag (always ≤ the ceiling, never open-ended); the custom path
    resolves its own hardLock client-side against hardlockCeilingMinutes."""
    presets = load_big_break_presets()
    activities = load_activities()
    reason = "today's training cap is used — you can still go for a walk"

    def _avail(intensity: str) -> dict:
        ok = is_available(intensity, cap_spent)
        return {"available": ok, "reason": None if ok else reason}

    return {
        "presets": [
            {
                "id": p.id,
                "activityId": p.activity_id,
                "name": p.name,
                "durationMinutes": p.duration_minutes,
                "description": p.description,
                "cue": p.cue,
                "rainOk": p.rain_ok,
                "intensity": p.intensity,
                "hardLock": hard_lock_enabled
                and big_break_is_hardlockable(p.duration_minutes, False),
                **_avail(p.intensity),
            }
            for p in presets
        ],
        "activities": [
            {
                "id": a.id,
                "name": a.name,
                "intensity": a.intensity,
                "rainOk": a.rain_ok,
                "defaultMinutes": a.default_minutes,
                "cue": a.cue,
                **_avail(a.intensity),
            }
            for a in activities
        ],
        "durationOptions": duration_picker_options(),
        "hardlockCeilingMinutes": BIG_BREAK_HARDLOCK_CEILING_MIN,
        "hardLockEnabled": hard_lock_enabled,
        "capSpent": cap_spent,
    }
