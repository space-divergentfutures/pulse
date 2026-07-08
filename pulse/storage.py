"""Local SQLite storage (spec §8) — the private source of truth.

Local-first, zero-setup, fully offline. **Nothing here contains window titles, app
names, or keystroke data** (§8, §13) — only aggregates and self-reported ratings.

ID and merge rules designed in now because they are painful to retrofit (§8):
- every row has a UUID primary key and a ``machine_id`` — records from two machines can
  never collide or overwrite each other.
- daily active-time totals are stored per machine and **summed** at display, never
  merged destructively.
- WAL mode, so reads and the background writer don't block each other.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid
from datetime import date as _date
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Daily accumulated active minutes, PER MACHINE (summed at display, never overwritten).
CREATE TABLE IF NOT EXISTS active_time (
    machine_id     TEXT NOT NULL,
    day            TEXT NOT NULL,          -- ISO date, local
    active_minutes REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (machine_id, day)
);

-- One-tap block ratings (§7 Stage 1) + the optional later dimensions (§7 Stage 2/3).
CREATE TABLE IF NOT EXISTS checkins (
    id         TEXT PRIMARY KEY,           -- UUID
    machine_id TEXT NOT NULL,
    ts         REAL NOT NULL,              -- epoch seconds
    day        TEXT NOT NULL,              -- ISO date, local (for distinct-day counts)
    rating     INTEGER,                    -- NULL when skipped
    block_type TEXT,                       -- Stage 2 (optional)
    energy     INTEGER,                    -- Stage 2 (optional)
    note       TEXT,                       -- Stage 3 (optional)
    skipped    INTEGER NOT NULL DEFAULT 0  -- a soft signal, logged without guilt (§7)
);
CREATE INDEX IF NOT EXISTS idx_checkins_ts ON checkins (ts);
"""


def default_db_path() -> Path:
    """%LOCALAPPDATA%\\PULSE\\pulse.db on Windows; home dir elsewhere (§8)."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "PULSE" / "pulse.db"


def _today_iso() -> str:
    return _date.today().isoformat()


class PulseStorage:
    def __init__(self, db_path: str | os.PathLike | None = None) -> None:
        raw = str(db_path) if db_path is not None else str(default_db_path())
        self.path = raw
        if raw != ":memory:":
            Path(raw).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: the poll loop and the GUI thread both touch storage;
        # every mutation is serialized behind self._lock.
        self._conn = sqlite3.connect(raw, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self.machine_id = self._get_or_create_machine_id()

    # --- machine identity ------------------------------------------------------

    def _get_or_create_machine_id(self) -> str:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'machine_id'"
        ).fetchone()
        if row is not None:
            return row["value"]
        mid = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES ('machine_id', ?)", (mid,)
            )
            self._conn.commit()
        return mid

    # --- check-ins -------------------------------------------------------------

    def add_checkin(
        self,
        rating: int | None,
        *,
        block_type: str | None = None,
        energy: int | None = None,
        note: str | None = None,
        skipped: bool = False,
        ts: float | None = None,
    ) -> str:
        """Record a block rating (or a skip). Returns the new UUID."""
        cid = str(uuid.uuid4())
        ts = time.time() if ts is None else ts
        day = _date.fromtimestamp(ts).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO checkins "
                "(id, machine_id, ts, day, rating, block_type, energy, note, skipped) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    cid,
                    self.machine_id,
                    ts,
                    day,
                    None if skipped else rating,
                    block_type,
                    energy,
                    note,
                    1 if skipped else 0,
                ),
            )
            self._conn.commit()
        return cid

    def recent_ratings(self, limit: int = 40) -> list[dict]:
        """Most recent NON-skipped ratings, oldest-first, for the graph dots."""
        rows = self._conn.execute(
            "SELECT id, ts, rating FROM checkins "
            "WHERE skipped = 0 AND rating IS NOT NULL "
            "ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [{"id": r["id"], "ts": r["ts"], "rating": r["rating"]} for r in reversed(rows)]

    def counted_checkins(self) -> int:
        """Non-skipped ratings — what the unlock meter counts toward the floor (§7)."""
        return self._conn.execute(
            "SELECT COUNT(*) AS n FROM checkins WHERE skipped = 0 AND rating IS NOT NULL"
        ).fetchone()["n"]

    def distinct_rating_days(self) -> int:
        """Distinct days with a non-skipped rating — the "5 across 3 days" rule (§7)."""
        return self._conn.execute(
            "SELECT COUNT(DISTINCT day) AS n FROM checkins "
            "WHERE skipped = 0 AND rating IS NOT NULL"
        ).fetchone()["n"]

    def checkins_on(self, day: str | None = None) -> int:
        day = day or _today_iso()
        return self._conn.execute(
            "SELECT COUNT(*) AS n FROM checkins WHERE day = ? AND skipped = 0", (day,)
        ).fetchone()["n"]

    # --- active time (per machine, summed at display) --------------------------

    def add_active_minutes(self, minutes: float, day: str | None = None) -> None:
        if minutes <= 0:
            return
        day = day or _today_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO active_time (machine_id, day, active_minutes) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(machine_id, day) DO UPDATE SET "
                "active_minutes = active_minutes + excluded.active_minutes",
                (self.machine_id, day, float(minutes)),
            )
            self._conn.commit()

    def active_minutes_total(self, day: str | None = None) -> float:
        """Summed across ALL machines for the day (the non-destructive merge, §8)."""
        day = day or _today_iso()
        row = self._conn.execute(
            "SELECT COALESCE(SUM(active_minutes), 0) AS total FROM active_time WHERE day = ?",
            (day,),
        ).fetchone()
        return float(row["total"])

    # --- lifecycle -------------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            self._conn.close()
