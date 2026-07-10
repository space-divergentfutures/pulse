"""Tests for the day plan + reading session scheduling (pulse.dayplan + storage)."""

import pytest

from pulse.dayplan import reading_due, reading_time_for
from pulse.export import export_data
from pulse.storage import PulseStorage

NOW = 1_750_000_000.0  # arbitrary fixed epoch


# ---------------------------------------------------------------------------
# reading_time_for — pure scheduling maths
# ---------------------------------------------------------------------------

def test_long_day_schedules_at_midpoint():
    at = reading_time_for(6.0, 4.0, NOW)
    assert at == NOW + 3.0 * 3600.0

def test_exactly_min_hours_schedules():
    at = reading_time_for(4.0, 4.0, NOW)
    assert at == NOW + 2.0 * 3600.0

def test_short_day_no_reading():
    assert reading_time_for(3.0, 4.0, NOW) is None

def test_skipped_plan_no_reading():
    assert reading_time_for(None, 4.0, NOW) is None

def test_lower_threshold_allows_short_days():
    assert reading_time_for(2.0, 1.0, NOW) == NOW + 3600.0


# ---------------------------------------------------------------------------
# reading_due
# ---------------------------------------------------------------------------

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
# storage.day_plans
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    s = PulseStorage(str(tmp_path / "dayplan_test.db"))
    yield s
    s.close()


def test_no_plan_initially(store):
    assert store.day_plan_today() is None

def test_plan_round_trip(store):
    store.record_day_plan(6.0, NOW + 3 * 3600.0)
    plan = store.day_plan_today()
    assert plan is not None
    assert plan["planned_hours"] == 6.0
    assert plan["reading_at"] == NOW + 3 * 3600.0
    assert plan["reading_done"] == 0

def test_skipped_plan_stored(store):
    store.record_day_plan(None, None)
    plan = store.day_plan_today()
    assert plan is not None
    assert plan["planned_hours"] is None
    assert plan["reading_at"] is None

def test_mark_reading_done(store):
    store.record_day_plan(8.0, NOW)
    store.mark_reading_done()
    assert store.day_plan_today()["reading_done"] == 1

def test_reading_break_layer_recorded(store):
    store.record_break("reading", "honor", "completed", 1800.0)
    row = store.fetch_table("breaks")[0]
    assert row["layer"] == "reading"
    assert row["duration_s"] == 1800.0

def test_reading_does_not_count_toward_training_cap(store):
    store.record_break("reading", "honor", "completed", 1800.0)
    assert store.training_count_today() == 0

def test_day_plans_exportable(store, tmp_path):
    store.record_day_plan(6.0, NOW + 3 * 3600.0)
    files = export_data(store, tmp_path / "out", fmt="csv")
    assert any("day_plans" in f.name for f in files)
