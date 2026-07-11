"""Tests for the Big Break activity menu + duration picker
(PULSE-BIG-BREAK-MENU-BUILD-SPEC-v1.md §5 — the 6 mandated test groups)."""

import sqlite3

import pytest

from pulse.export import export_data
from pulse.storage import PulseStorage
from pulse.training import (
    BIG_BREAK_HARDLOCK_CEILING_MIN,
    activity_intensity,
    big_break_is_hardlockable,
    duration_picker_options,
    is_available,
    load_activities,
    load_big_break_presets,
)


@pytest.fixture
def store(tmp_path):
    s = PulseStorage(str(tmp_path / "bigbreak_test.db"))
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Group 1 — migration: old DB gains the two columns; existing rows intact
# ---------------------------------------------------------------------------

def test_migration_adds_columns_and_preserves_rows(tmp_path):
    db_path = str(tmp_path / "old.db")

    # Build a pre-migration `breaks` table by hand (no activity_type/activity_minutes)
    # and insert a row, simulating a database from before this feature existed.
    raw = sqlite3.connect(db_path)
    raw.execute(
        "CREATE TABLE breaks (id TEXT PRIMARY KEY, machine_id TEXT, ts REAL, "
        "day TEXT, layer TEXT, enforcement TEXT, outcome TEXT, duration_s REAL)"
    )
    raw.execute(
        "INSERT INTO breaks VALUES ('old-1', 'machine-x', 1000.0, '2026-01-01', "
        "'big', 'honor', 'completed', 720.0)"
    )
    raw.commit()
    raw.close()

    store = PulseStorage(db_path)
    try:
        cols = {r["name"] for r in store._conn.execute("PRAGMA table_info(breaks)")}
        assert "activity_type" in cols
        assert "activity_minutes" in cols

        row = store._conn.execute(
            "SELECT * FROM breaks WHERE id = 'old-1'"
        ).fetchone()
        assert row["duration_s"] == 720.0
        assert row["outcome"] == "completed"
        assert row["activity_type"] is None
        assert row["activity_minutes"] is None
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Group 2 — cap logic: hard consumes cap; easy never does;
#           easy offerable at cap=spent; hard not
# ---------------------------------------------------------------------------

def test_hard_consumes_cap(store):
    store.record_break("big", "honor", "completed", 900.0,
                        activity_type="run", activity_minutes=15.0)
    assert store.training_count_today() == 1


def test_easy_never_consumes_cap(store):
    store.record_break("big", "honor", "completed", 1200.0,
                        activity_type="walk", activity_minutes=20.0)
    assert store.training_count_today() == 0


def test_mixed_hard_and_easy_only_hard_counted(store):
    store.record_break("big", "honor", "completed", 1200.0,
                        activity_type="walk", activity_minutes=20.0)
    store.record_break("big", "honor", "completed", 900.0,
                        activity_type="run", activity_minutes=15.0)
    store.record_break("big", "honor", "completed", 2700.0,
                        activity_type="walk", activity_minutes=45.0)
    assert store.training_count_today() == 1


def test_easy_offerable_when_cap_spent():
    assert is_available("easy", cap_spent=True) is True


def test_hard_not_offerable_when_cap_spent():
    assert is_available("hard", cap_spent=True) is False


def test_both_offerable_when_cap_not_spent():
    assert is_available("easy", cap_spent=False) is True
    assert is_available("hard", cap_spent=False) is True


# ---------------------------------------------------------------------------
# Group 3 — hard-lock ceiling: 90 min lockable; 91 min honour-based;
#           open-ended honour-based, always
# ---------------------------------------------------------------------------

def test_ceiling_value_is_90():
    assert BIG_BREAK_HARDLOCK_CEILING_MIN == 90.0

def test_90_minutes_is_hardlockable():
    assert big_break_is_hardlockable(90.0, open_ended=False) is True

def test_91_minutes_is_not_hardlockable():
    assert big_break_is_hardlockable(91.0, open_ended=False) is False

def test_open_ended_never_hardlockable_regardless_of_minutes():
    assert big_break_is_hardlockable(None, open_ended=True) is False
    assert big_break_is_hardlockable(5.0, open_ended=True) is False

def test_short_duration_is_hardlockable():
    assert big_break_is_hardlockable(12.0, open_ended=False) is True


# ---------------------------------------------------------------------------
# Group 4 — duration-step helper: 1/5/15-min step boundaries correct;
#           open-ended sentinel handled
# ---------------------------------------------------------------------------

def test_first_entry_is_open_ended_sentinel():
    opts = duration_picker_options()
    assert opts[0]["minutes"] is None
    assert "Open-ended" in opts[0]["label"]

def test_one_minute_steps_up_to_30():
    opts = duration_picker_options()
    minutes = [o["minutes"] for o in opts if o["minutes"] is not None]
    one_min_zone = [m for m in minutes if m <= 30]
    assert one_min_zone == [float(m) for m in range(1, 31)]

def test_boundary_from_1min_to_5min_steps_at_30():
    opts = duration_picker_options()
    minutes = [o["minutes"] for o in opts if o["minutes"] is not None]
    idx_30 = minutes.index(30.0)
    assert minutes[idx_30 + 1] == 35.0  # jumps by 5, not 31

def test_five_minute_steps_up_to_120():
    opts = duration_picker_options()
    minutes = [o["minutes"] for o in opts if o["minutes"] is not None]
    five_min_zone = [m for m in minutes if 30 < m <= 120]
    assert five_min_zone == [float(m) for m in range(35, 121, 5)]

def test_boundary_from_5min_to_15min_steps_at_120():
    opts = duration_picker_options()
    minutes = [o["minutes"] for o in opts if o["minutes"] is not None]
    idx_120 = minutes.index(120.0)
    assert minutes[idx_120 + 1] == 135.0  # jumps by 15, not 125

def test_fifteen_minute_steps_up_to_240():
    opts = duration_picker_options()
    minutes = [o["minutes"] for o in opts if o["minutes"] is not None]
    fifteen_min_zone = [m for m in minutes if m > 120]
    assert fifteen_min_zone == [float(m) for m in range(135, 241, 15)]

def test_last_entry_is_four_hours():
    opts = duration_picker_options()
    assert opts[-1]["minutes"] == 240.0


# ---------------------------------------------------------------------------
# Group 5 — open-ended completion logs measured elapsed minutes,
#           not a preset duration
# ---------------------------------------------------------------------------

def test_open_ended_logs_measured_elapsed(store):
    # 47.3 min actually elapsed — not any of the fixed preset durations (all 12).
    store.record_break("big", "honor", "completed", 47.3 * 60.0,
                        activity_type="bike", activity_minutes=47.3)
    row = store.fetch_table("breaks")[0]
    assert row["activity_minutes"] == 47.3
    assert row["activity_minutes"] != 12.0
    assert row["duration_s"] == pytest.approx(47.3 * 60.0)

def test_open_ended_export_includes_activity_columns(store, tmp_path):
    store.record_break("big", "honor", "completed", 1975.0,
                        activity_type="gym", activity_minutes=32.9)
    files = export_data(store, tmp_path / "out", fmt="json")
    breaks_file = next(f for f in files if "breaks" in f.name)
    import json
    rows = json.loads(breaks_file.read_text(encoding="utf-8"))
    assert rows[0]["activity_type"] == "gym"
    assert rows[0]["activity_minutes"] == 32.9


# ---------------------------------------------------------------------------
# Group 6 — preset loader: all 5 presets returned, stable ids,
#           activity linkage resolves
# ---------------------------------------------------------------------------

def test_preset_loader_returns_all_five():
    presets = load_big_break_presets()
    assert len(presets) == 5

def test_preset_ids_are_stable():
    presets = load_big_break_presets()
    ids = {p.id for p in presets}
    assert ids == {
        "sprint_intervals", "easy_run", "bike_intervals", "kb_amrap", "jump_rope",
    }

def test_preset_activity_linkage_resolves():
    activity_ids = {a.id for a in load_activities()}
    for p in load_big_break_presets():
        assert p.activity_id in activity_ids
        assert p.intensity == activity_intensity(p.activity_id)

def test_preset_cue_and_rain_ok_match_activity():
    activities = {a.id: a for a in load_activities()}
    for p in load_big_break_presets():
        act = activities[p.activity_id]
        assert p.cue == act.cue
        assert p.rain_ok == act.rain_ok
