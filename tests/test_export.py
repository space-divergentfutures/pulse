"""Tests for the local data export (pulse.export + storage.fetch_table)."""

import csv
import json
import time

import pytest

from pulse.export import export_data
from pulse.storage import PulseStorage


@pytest.fixture
def store(tmp_path):
    s = PulseStorage(str(tmp_path / "export_test.db"))
    yield s
    s.close()


def _seed(store):
    store.add_checkin(7)
    store.add_checkin(4, block_type="deep work", note="flowed")
    store.add_checkin(None, skipped=True)
    store.record_break("training", "session_card", "completed", 300.0)
    store.record_meal_prompt(
        "lunch", "yes", food_detail="medium", water_amount="glass"
    )
    store.add_active_minutes(42.5)


# ---------------------------------------------------------------------------
# storage.fetch_table
# ---------------------------------------------------------------------------

def test_fetch_table_returns_rows(store):
    _seed(store)
    assert len(store.fetch_table("checkins")) == 3
    assert len(store.fetch_table("breaks")) == 1
    assert len(store.fetch_table("meal_prompts")) == 1
    assert len(store.fetch_table("active_time")) == 1

def test_fetch_table_whitelist(store):
    for forbidden in ("meta", "settings", "sync_log", "checkins; DROP TABLE meta"):
        with pytest.raises(ValueError):
            store.fetch_table(forbidden)

def test_fetch_table_epoch_cutoff(store):
    old_ts = time.time() - 30 * 86400.0
    store.add_checkin(5, ts=old_ts)
    store.add_checkin(8)
    assert len(store.fetch_table("checkins")) == 2
    recent = store.fetch_table("checkins", days=7)
    assert len(recent) == 1
    assert recent[0]["rating"] == 8

def test_fetch_table_isodate_cutoff(store):
    old_ts = time.time() - 30 * 86400.0
    store.record_meal_prompt("lunch", "yes", ts=old_ts)
    store.record_meal_prompt("dinner", "no", 20.0)
    assert len(store.fetch_table("meal_prompts")) == 2
    assert len(store.fetch_table("meal_prompts", days=7)) == 1

def test_fetch_table_meal_detail_columns(store):
    store.record_meal_prompt("lunch", "yes", food_detail="light", water_amount="plenty")
    row = store.fetch_table("meal_prompts")[0]
    assert row["food_detail"] == "light"
    assert row["water_amount"] == "plenty"


# ---------------------------------------------------------------------------
# export_data
# ---------------------------------------------------------------------------

def test_export_csv_creates_files_and_manifest(store, tmp_path):
    _seed(store)
    out = tmp_path / "out"
    files = export_data(store, out, fmt="csv")

    names = [f.name for f in files]
    assert len(files) == 4
    for table in ("checkins", "breaks", "meal_prompts", "active_time"):
        assert any(table in n for n in names)
    assert all(f.suffix == ".csv" for f in files)

    manifest = out / "PULSE_EXPORT_README.txt"
    assert manifest.exists()
    content = manifest.read_text(encoding="utf-8")
    assert "PRIVACY" in content
    assert "checkins" in content
    assert "never stores window titles" in content

def test_export_csv_readable_and_has_ts_iso(store, tmp_path):
    _seed(store)
    files = export_data(store, tmp_path / "out", fmt="csv")
    checkins = next(f for f in files if "checkins" in f.name)
    with checkins.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    assert "ts_iso" in rows[0]
    assert rows[0]["ts_iso"]  # non-empty, human-readable

def test_export_json_valid(store, tmp_path):
    _seed(store)
    files = export_data(store, tmp_path / "out", fmt="json")
    assert all(f.suffix == ".json" for f in files)
    breaks = next(f for f in files if "breaks" in f.name)
    data = json.loads(breaks.read_text(encoding="utf-8"))
    assert data[0]["layer"] == "training"
    assert data[0]["outcome"] == "completed"

def test_export_empty_db_writes_nothing(store, tmp_path):
    out = tmp_path / "out"
    files = export_data(store, out, fmt="csv")
    assert files == []
    assert not (out / "PULSE_EXPORT_README.txt").exists()

def test_export_days_filter(store, tmp_path):
    old_ts = time.time() - 30 * 86400.0
    store.add_checkin(5, ts=old_ts)
    files = export_data(store, tmp_path / "out", fmt="csv", days=7)
    assert files == []  # the only row is outside the window
