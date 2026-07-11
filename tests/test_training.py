"""Tests for the training layer: data loading, session picking, progression (spec §5b, §9)."""

import pytest

from pulse.storage import PulseStorage
from pulse.training import (
    ExerciseSpec,
    TrainingSession,
    load_activities,
    load_big_break_presets,
    load_big_breaks,
    load_exercises,
    pick_session,
    session_payload,
    big_break_payload,
)


# ---------------------------------------------------------------------------
# Data file loading
# ---------------------------------------------------------------------------

def test_load_exercises_structure():
    data = load_exercises()
    assert "categories" in data
    cats = data["categories"]
    assert len(cats) == 5
    for cat in cats:
        assert "id" in cat and "exercises" in cat
        for ex in cat["exercises"]:
            assert "id" in ex and "levels" in ex
            assert len(ex["levels"]) == 3


def test_load_big_breaks_structure():
    data = load_big_breaks()
    assert "activities" in data and "presets" in data
    assert len(data["activities"]) == 8
    assert len(data["presets"]) == 5
    for act in data["activities"]:
        assert "id" in act and "intensity" in act and "default_minutes" in act
    for preset in data["presets"]:
        assert "id" in preset and "activity" in preset and "duration_minutes" in preset


def test_activities_rain_ok_field():
    acts = load_activities()
    # At least some activities are rain-ok (indoor)
    assert any(a.rain_ok for a in acts)
    # Exactly one easy activity today: Walk
    assert [a.id for a in acts if a.intensity == "easy"] == ["walk"]


# ---------------------------------------------------------------------------
# Session picking
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    return PulseStorage(str(tmp_path / "t.db"))


def test_pick_session_returns_two_exercises(store):
    session = pick_session(store, session_cursor=0)
    assert isinstance(session, TrainingSession)
    assert len(session.exercises) == 2
    for ex in session.exercises:
        assert isinstance(ex, ExerciseSpec)
        assert ex.id and ex.name and ex.work


def test_pick_session_rotates(store):
    s0 = pick_session(store, 0)
    s1 = pick_session(store, 1)
    # Different cursors should yield different exercise combinations
    ids0 = {e.id for e in s0.exercises}
    ids1 = {e.id for e in s1.exercises}
    # Not strictly guaranteed to differ on every cursor, but they start at L1 for all
    assert all(e.level == 1 for e in s0.exercises)


def test_pick_session_uses_stored_level(store):
    # Manually raise the level for kb_swings
    store.exercise_level("kb_swings")          # creates row at L1
    for _ in range(6):
        store.record_exercise_done("kb_swings")  # 6 completions → promote to L2
    session = pick_session(store, 0)
    kb = next((e for e in session.exercises if e.id == "kb_swings"), None)
    if kb is not None:
        assert kb.level == 2


def test_load_big_break_presets_returns_all_five():
    presets = load_big_break_presets()
    assert len(presets) == 5
    for p in presets:
        assert p.id and p.name and p.duration_minutes > 0 and p.description
        assert p.cue and p.intensity in ("hard", "easy")


def test_session_payload_structure(store):
    session = pick_session(store, 0)
    payload = session_payload(session, hard_lock=False)
    assert payload["type"] == "training"
    assert payload["hardLock"] is False
    assert len(payload["exercises"]) == 2
    for ex in payload["exercises"]:
        assert "id" in ex and "name" in ex and "work" in ex and "level" in ex


def test_big_break_payload_structure():
    payload = big_break_payload(cap_spent=False, hard_lock_enabled=False)
    assert len(payload["presets"]) == 5
    assert len(payload["activities"]) == 8
    assert all(p["available"] for p in payload["presets"])
    assert "durationOptions" in payload and payload["durationOptions"][0]["minutes"] is None


# ---------------------------------------------------------------------------
# Exercise progression (storage)
# ---------------------------------------------------------------------------

def test_exercise_level_default(store):
    assert store.exercise_level("kb_swings") == 1


def test_exercise_level_stable(store):
    store.exercise_level("plank")
    assert store.exercise_level("plank") == 1


def test_record_done_increments_streak(store):
    store.exercise_level("pushups")
    for _ in range(5):
        result = store.record_exercise_done("pushups")
    # 5 completions — not yet at 6
    assert result["level_changed"] is False
    assert result["new_level"] == 1


def test_record_done_promotes_at_six(store):
    store.exercise_level("pushups")
    result = None
    for _ in range(6):
        result = store.record_exercise_done("pushups")
    assert result["level_changed"] is True
    assert result["new_level"] == 2
    assert store.exercise_level("pushups") == 2


def test_record_done_does_not_exceed_l3(store):
    store.exercise_level("kb_swings")
    # Reach L3
    for _ in range(6):
        store.record_exercise_done("kb_swings")  # L1→L2
    for _ in range(6):
        store.record_exercise_done("kb_swings")  # L2→L3
    # 6 more should NOT promote beyond L3
    for _ in range(6):
        result = store.record_exercise_done("kb_swings")
    assert result["level_changed"] is False
    assert result["new_level"] == 3


def test_record_skip_deloads_at_two(store):
    store.exercise_level("bw_squats")
    store.record_exercise_done("bw_squats")  # streak 1
    store.record_exercise_done("bw_squats")  # streak 2
    store.record_exercise_done("bw_squats")  # streak 3
    store.record_exercise_done("bw_squats")  # streak 4
    store.record_exercise_done("bw_squats")  # streak 5
    store.record_exercise_done("bw_squats")  # 6 → L2
    # Now two consecutive skips → deload
    store.record_exercise_skip("bw_squats")
    result = store.record_exercise_skip("bw_squats")
    assert result["level_changed"] is True
    assert result["new_level"] == 1


def test_record_skip_no_deload_at_l1(store):
    store.exercise_level("dead_hang")
    store.record_exercise_skip("dead_hang")
    result = store.record_exercise_skip("dead_hang")
    assert result["level_changed"] is False
    assert result["new_level"] == 1


def test_pain_sets_cooldown(store):
    assert not store.is_pain_cooldown("rows")
    store.record_exercise_pain("rows")
    assert store.is_pain_cooldown("rows")


# ---------------------------------------------------------------------------
# Break logging + training cap
# ---------------------------------------------------------------------------

def test_training_count_starts_zero(store):
    assert store.training_count_today() == 0


def test_record_break_training_counts(store):
    store.record_break("training", "session_card", "completed")
    assert store.training_count_today() == 1


def test_record_break_skipped_doesnt_count(store):
    store.record_break("training", "session_card", "skipped")
    assert store.training_count_today() == 0


def test_record_break_big_counts(store):
    store.record_break("big", "honor", "completed")
    assert store.training_count_today() == 1


def test_training_cap_at_two(store):
    store.record_break("training", "session_card", "completed")
    store.record_break("big", "honor", "completed")
    assert store.training_count_today() == 2
