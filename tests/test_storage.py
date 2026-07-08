"""SQLite storage + unlock-meter math (spec §7, §8)."""

from __future__ import annotations

import time

import pytest

from pulse.config import TimingConfig
from pulse.reflection import graph_payload
from pulse.storage import PulseStorage


@pytest.fixture
def store(tmp_path):
    s = PulseStorage(tmp_path / "pulse.db")
    yield s
    s.close()


def test_wal_mode_enabled(store):
    mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_machine_id_stable_across_reopen(tmp_path):
    p = tmp_path / "pulse.db"
    s1 = PulseStorage(p)
    mid = s1.machine_id
    s1.close()
    s2 = PulseStorage(p)
    assert s2.machine_id == mid  # persisted, not regenerated
    s2.close()


def test_checkin_ids_are_unique_uuids(store):
    ids = {store.add_checkin(7) for _ in range(20)}
    assert len(ids) == 20
    assert all(len(i) == 36 for i in ids)  # uuid4 string form


def test_counted_checkins_excludes_skips(store):
    store.add_checkin(8)
    store.add_checkin(5)
    store.add_checkin(None, skipped=True)  # a skip is logged but not counted (§7)
    assert store.counted_checkins() == 2


def test_recent_ratings_oldest_first_and_no_skips(store):
    t = time.time()
    store.add_checkin(3, ts=t - 30)
    store.add_checkin(None, skipped=True, ts=t - 20)
    store.add_checkin(9, ts=t - 10)
    ratings = [p["rating"] for p in store.recent_ratings()]
    assert ratings == [3, 9]  # chronological, skip excluded


def test_distinct_rating_days(store):
    day1 = time.mktime(time.strptime("2026-07-01", "%Y-%m-%d"))
    day2 = time.mktime(time.strptime("2026-07-02", "%Y-%m-%d"))
    store.add_checkin(7, ts=day1)
    store.add_checkin(6, ts=day1)
    store.add_checkin(8, ts=day2)
    assert store.distinct_rating_days() == 2


def test_active_minutes_accumulate_and_sum(store):
    store.add_active_minutes(10, day="2026-07-08")
    store.add_active_minutes(5, day="2026-07-08")
    assert store.active_minutes_total(day="2026-07-08") == 15.0
    store.add_active_minutes(-3, day="2026-07-08")  # guard: non-positive ignored
    assert store.active_minutes_total(day="2026-07-08") == 15.0


def test_unlock_meter_progresses_to_floor(store):
    cfg = TimingConfig()  # floor = 15
    assert graph_payload(store, cfg)["meter_pct"] == 0
    for _ in range(3):
        store.add_checkin(7)
    p = graph_payload(store, cfg)
    assert p["count"] == 3
    assert p["meter_pct"] == round(3 / 15 * 100)  # ~20%
    assert p["unlocked"] is False


def test_unlock_meter_caps_at_100(store):
    cfg = TimingConfig(insight_min_observations=5)
    for _ in range(9):
        store.add_checkin(6)
    p = graph_payload(store, cfg)
    assert p["meter_pct"] == 100
    assert p["unlocked"] is True
