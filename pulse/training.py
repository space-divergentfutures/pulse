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
class BigBreakOption:
    id: str
    name: str
    duration_s: float
    description: str
    cue: str
    rain_ok: bool


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_exercises() -> dict:
    with EXERCISES_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def load_big_breaks() -> dict:
    with BIG_BREAK_FILE.open(encoding="utf-8") as f:
        return json.load(f)


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


def pick_big_break_options(n: int = 3) -> list[BigBreakOption]:
    """Return up to n Big Break options from the pool."""
    data = load_big_breaks()
    return [
        BigBreakOption(
            id=o["id"],
            name=o["name"],
            duration_s=o["duration_minutes"] * 60.0,
            description=o["description"],
            cue=o["cue"],
            rain_ok=o["rain_ok"],
        )
        for o in data["options"][:n]
    ]


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


def big_break_payload(options: list[BigBreakOption]) -> dict:
    return {
        "type": "big_break",
        "options": [
            {
                "id": o.id,
                "name": o.name,
                "duration_s": o.duration_s,
                "description": o.description,
                "cue": o.cue,
                "rain_ok": o.rain_ok,
            }
            for o in options
        ],
    }
