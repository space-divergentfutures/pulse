"""Tests for the sitting-plan pure functions + storage API
(pulse.dayplan + storage's day_plans/sitting methods).

Sitting-boundary integration tests (midnight crossing, suspend, zombie cleanup,
etc.) live in tests/test_sitting.py — this file covers the scheduling maths and
the CRUD surface in isolation.
"""

import pytest

from pulse.dayplan import is_qualifying_gap, reading_due, reading_time_for
from pulse.export import export_data
from pulse.storage import PulseStorage

NOW = 1_750_000_000.0  # arbitrary fixed epoch


# ---------------------------------------------------------------------------
# reading_time_for / reading_due — pure scheduling maths (unchanged logic)
# ---------------------------------------------------------------------------

def test_long_sitting_schedules_at_midpoint():
    at = reading_time_for(6.0, 4.0, NOW)
    assert at == NOW + 3.0 * 3600.0

def test_exactly_min_hours_schedules():
    at = reading_time_for(4.0, 4.0, NOW)
    assert at == NOW + 2.0 * 3600.0

def test_short_sitting_no_reading():
    assert reading_time_for(3.0, 4.0, NOW) is None

def test_skipped_plan_no_reading():
    assert reading_time_for(None, 4.0, NOW) is None

def test_lower_threshold_allows_short_sittings():
    assert reading_time_for(2.0, 1.0, NOW) == NOW + 3600.0

def test_not_due_before_time():
    at = NOW + 100.0
    assert not reading_due(at, False, NOW)

def test_due_at_time():
    assert reading_due(NOW, False, NOW)
    assert reading_due(NOW - 5.0, False, NOW)

def test_not_due_when_done():
    assert not reading_due(NOW - 5.0, True, NOW)

def test_not_due_when_unscheduled():
    assert not reading_due(None, False, NOW)


# ---------------------------------------------------------------------------
# is_qualifying_gap — pure sitting-boundary logic
# ---------------------------------------------------------------------------

def test_active_presence_never_qualifies():
    assert not is_qualifying_gap(True, 999999.0, 4.0, suspend_detected=False)

def test_suspend_always_qualifies_any_magnitude():
    assert is_qualifying_gap(False, 1.0, 4.0, suspend_detected=True)
    assert is_qualifying_gap(True, 0.0, 4.0, suspend_detected=True)

def test_short_idle_does_not_qualify():
    assert not is_qualifying_gap(False, 40 * 60.0, 4.0, suspend_detected=False)

def test_idle_past_threshold_qualifies():
    assert is_qualifying_gap(False, 4 * 3600.0 + 1, 4.0, suspend_detected=False)


# ---------------------------------------------------------------------------
# storage: sitting CRUD
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    s = PulseStorage(str(tmp_path / "dayplan_test.db"))
    yield s
    s.close()


def test_no_open_sitting_initially(store):
    assert store.open_sitting_row() is None

def test_open_sitting_round_trip(store):
    sid = store.open_sitting(NOW)
    row = store.open_sitting_row()
    assert row is not None
    assert row["id"] == sid
    assert row["started_ts"] == NOW
    assert row["ended_ts"] is None
    assert row["planned_hours"] is None

def test_set_sitting_plan(store):
    sid = store.open_sitting(NOW)
    store.set_sitting_plan(sid, 6.0, NOW + 3 * 3600.0)
    row = store.open_sitting_row()
    assert row["planned_hours"] == 6.0
    assert row["reading_at"] == NOW + 3 * 3600.0

def test_skipped_plan_stays_open_with_nulls(store):
    sid = store.open_sitting(NOW)
    # Skip: never call set_sitting_plan — row stays as opened.
    row = store.open_sitting_row()
    assert row["id"] == sid
    assert row["planned_hours"] is None
    assert row["reading_at"] is None

def test_close_sitting(store):
    sid = store.open_sitting(NOW)
    store.close_sitting(sid, NOW + 3600.0)
    assert store.open_sitting_row() is None

def test_close_sitting_backdated_end(store):
    sid = store.open_sitting(NOW)
    ended = NOW + 5000.0  # backdated to a last-active moment, not "now"
    store.close_sitting(sid, ended)
    row = store._conn.execute(
        "SELECT * FROM day_plans WHERE id = ?", (sid,)
    ).fetchone()
    assert row["ended_ts"] == ended

def test_mark_reading_done(store):
    sid = store.open_sitting(NOW)
    store.set_sitting_plan(sid, 8.0, NOW)
    store.mark_reading_done(sid)
    assert store.open_sitting_row()["reading_done"] == 1

def test_new_sitting_after_close(store):
    sid1 = store.open_sitting(NOW)
    store.close_sitting(sid1, NOW + 3600.0)
    sid2 = store.open_sitting(NOW + 7200.0)
    assert sid2 != sid1
    assert store.open_sitting_row()["id"] == sid2

def test_reading_break_layer_recorded(store):
    store.record_break("reading", "honor", "completed", 1800.0)
    row = store.fetch_table("breaks")[0]
    assert row["layer"] == "reading"
    assert row["duration_s"] == 1800.0

def test_reading_does_not_count_toward_training_cap(store):
    store.record_break("reading", "honor", "completed", 1800.0)
    assert store.training_count_today() == 0

def test_day_plans_exportable(store, tmp_path):
    sid = store.open_sitting(NOW)
    store.set_sitting_plan(sid, 6.0, NOW + 3 * 3600.0)
    files = export_data(store, tmp_path / "out", fmt="csv")
    assert any("day_plans" in f.name for f in files)
