"""Sitting-boundary integration tests
(PULSE-SITTING-PLAN-BUILD-SPEC-v1.md §5 — the 7 mandated test groups).

Drives PulseApp._tick_sitting directly with an injected wall-clock (`now`) and
controlled presence/idle/suspend signals — the same headless pattern used for
the reading-session and Big Break app-level verification. No real windows are
created; PulseApp.__init__ never touches pywebview, only .run()/.create() do.
"""

import sqlite3

import pytest

from pulse.app import PulseApp
from pulse.presence import PresenceState
from pulse.state_machine import SessionState

NOW = 1_800_000_000.0
HOUR = 3600.0


@pytest.fixture
def app(tmp_path):
    a = PulseApp(db_path=str(tmp_path / "sitting.db"))
    a.settings.mark_first_run_complete()
    a.settings.set("sitting_gap_hours", 4.0)
    a._asked = []
    a.dayplan_card.ask = lambda hrs: a._asked.append(hrs)
    yield a
    a.storage.close()


def tick(app, presence, idle_seconds, suspend, now, state=SessionState.WORK):
    app._tick_sitting(presence, idle_seconds, suspend, state, now=now)


# ---------------------------------------------------------------------------
# Group 1 — midnight crossing: one sitting, one ask, no re-ask after midnight
# ---------------------------------------------------------------------------

def test_midnight_crossing_is_one_sitting_no_reask(app):
    # 23:00 start, active straight through to 01:30 — no gap anywhere.
    t = NOW
    tick(app, PresenceState.ACTIVE, 1.0, False, now=t)
    sitting_id = app._sitting_id
    assert len(app._asked) == 1

    for _ in range(10):  # 10 x 15-min active ticks = 2.5h, crossing "midnight"
        t += 15 * 60.0
        tick(app, PresenceState.ACTIVE, 1.0, False, now=t)

    assert app._sitting_id == sitting_id  # never closed
    assert len(app._asked) == 1           # never re-asked


# ---------------------------------------------------------------------------
# Group 2 — suspend overnight: sitting closes at last-active, new one asks
# ---------------------------------------------------------------------------

def test_suspend_overnight_closes_and_reopens(app):
    t = NOW
    tick(app, PresenceState.ACTIVE, 1.0, False, now=t)
    first_sitting = app._sitting_id
    last_active = t

    # Active for a bit longer before sleep at "23:00".
    t += 30 * 60.0
    tick(app, PresenceState.ACTIVE, 1.0, False, now=t)
    last_active = t

    # Machine suspends; engine detects it on the tick after waking at "08:00".
    wake_time = t + 9 * HOUR
    tick(app, PresenceState.AWAY, 5.0, True, now=wake_time)  # suspend_detected=True
    assert app._sitting_id is None

    closed = app.storage._conn.execute(
        "SELECT ended_ts FROM day_plans WHERE id = ?", (first_sitting,)
    ).fetchone()
    assert closed["ended_ts"] == last_active  # backdated, not the wake moment

    # First active tick after waking opens a fresh sitting and asks again.
    tick(app, PresenceState.ACTIVE, 1.0, False, now=wake_time + 5.0)
    assert app._sitting_id is not None
    assert app._sitting_id != first_sitting
    assert len(app._asked) == 2


# ---------------------------------------------------------------------------
# Group 3 — short gap: same sitting continues, no re-ask
# ---------------------------------------------------------------------------

def test_short_gap_does_not_end_sitting(app):
    t = NOW
    tick(app, PresenceState.ACTIVE, 1.0, False, now=t)
    sitting_id = app._sitting_id

    # 40-minute lunch break: AWAY, idle_seconds well under the 4h threshold.
    t += 40 * 60.0
    tick(app, PresenceState.AWAY, 40 * 60.0, False, now=t)
    assert app._sitting_id == sitting_id

    # Back at the desk — still the same sitting, no second ask.
    t += 5.0
    tick(app, PresenceState.ACTIVE, 1.0, False, now=t)
    assert app._sitting_id == sitting_id
    assert len(app._asked) == 1


# ---------------------------------------------------------------------------
# Group 4 — threshold edge: exactly sitting_gap_hours ends it; just under doesn't
# ---------------------------------------------------------------------------

def test_threshold_edge_just_under_stays_open(app):
    t = NOW
    tick(app, PresenceState.ACTIVE, 1.0, False, now=t)
    sitting_id = app._sitting_id
    tick(app, PresenceState.AWAY, 4 * HOUR - 1, False, now=t + 100)
    assert app._sitting_id == sitting_id

def test_threshold_edge_exactly_at_closes(app):
    t = NOW
    tick(app, PresenceState.ACTIVE, 1.0, False, now=t)
    tick(app, PresenceState.AWAY, 4 * HOUR, False, now=t + 100)
    assert app._sitting_id is None


# ---------------------------------------------------------------------------
# Group 5 — zombie cleanup: stale open sitting from a killed run gets closed
# ---------------------------------------------------------------------------

def test_zombie_sitting_closed_on_restart(tmp_path):
    db_path = str(tmp_path / "zombie.db")

    a1 = PulseApp(db_path=db_path)
    a1.settings.mark_first_run_complete()
    a1.settings.set("sitting_gap_hours", 4.0)
    stale_start = NOW - 6 * HOUR
    stale_id = a1.storage.open_sitting(stale_start)
    a1.storage.close()  # simulate the process being killed — no clean close_sitting call

    # "Restart" 6 hours later: a brand-new PulseApp instance on the same file.
    a2 = PulseApp(db_path=db_path)
    a2._asked = []
    a2.dayplan_card.ask = lambda hrs: a2._asked.append(hrs)
    tick(a2, PresenceState.ACTIVE, 1.0, False, now=NOW)

    stale_row = a2.storage._conn.execute(
        "SELECT ended_ts FROM day_plans WHERE id = ?", (stale_id,)
    ).fetchone()
    assert stale_row["ended_ts"] is not None  # closed, not left dangling

    assert a2._sitting_id is not None
    assert a2._sitting_id != stale_id  # a fresh sitting was opened
    assert len(a2._asked) == 1
    a2.storage.close()


# ---------------------------------------------------------------------------
# Group 6 — reading: pending offer doesn't survive sitting end;
#           midpoint computed from sitting start
# ---------------------------------------------------------------------------

def test_reading_offer_reset_on_sitting_end(app):
    t = NOW
    tick(app, PresenceState.ACTIVE, 1.0, False, now=t)
    app._on_day_planned(6.0)  # midpoint 3h out
    assert app._reading_at is not None

    # A suspend-scale gap ends the sitting before reading is due.
    tick(app, PresenceState.AWAY, 5.0, True, now=t + 60.0)
    assert app._sitting_id is None
    assert app._reading_at is None
    assert app._reading_pending is False

def test_reading_midpoint_uses_sitting_start_not_answer_time(app):
    t = NOW
    tick(app, PresenceState.ACTIVE, 1.0, False, now=t)
    # _on_day_planned reads no clock of its own — it anchors to the cached
    # sitting-start timestamp, so answering late never shifts the midpoint.
    app._on_day_planned(6.0)
    assert app._reading_at == t + 3 * HOUR


# ---------------------------------------------------------------------------
# Group 7 — migration: old day_plans rows intact, new columns NULL, exportable
# ---------------------------------------------------------------------------

def test_migration_adds_sitting_columns_preserves_old_rows(tmp_path):
    db_path = str(tmp_path / "old.db")

    raw = sqlite3.connect(db_path)
    raw.execute(
        "CREATE TABLE day_plans (id TEXT PRIMARY KEY, machine_id TEXT, date TEXT, "
        "planned_hours REAL, reading_at REAL, reading_done INTEGER, ts REAL)"
    )
    raw.execute(
        "INSERT INTO day_plans VALUES "
        "('old-1', 'machine-x', '2026-01-01', 5.0, 1700000000.0, 1, 1699990000.0)"
    )
    raw.commit()
    raw.close()

    from pulse.storage import PulseStorage
    store = PulseStorage(db_path)
    try:
        cols = {r["name"] for r in store._conn.execute("PRAGMA table_info(day_plans)")}
        assert "started_ts" in cols
        assert "ended_ts" in cols

        row = store._conn.execute(
            "SELECT * FROM day_plans WHERE id = 'old-1'"
        ).fetchone()
        assert row["planned_hours"] == 5.0
        assert row["reading_done"] == 1
        assert row["started_ts"] is None
        assert row["ended_ts"] is None

        from pulse.export import export_data
        files = export_data(store, tmp_path / "out", fmt="json")
        assert any("day_plans" in f.name for f in files)
    finally:
        store.close()
