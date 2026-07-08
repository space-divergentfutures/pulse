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

-- Tracked reflection dimensions (§7 Stage 2/3).
-- Enabled dimensions appear in the check-in card after their stage unlocks.
CREATE TABLE IF NOT EXISTS tracked_dimensions (
    machine_id TEXT NOT NULL,
    name       TEXT NOT NULL,   -- 'block_type' | 'note'
    enabled    INTEGER NOT NULL DEFAULT 1,
    added_ts   REAL NOT NULL,
    PRIMARY KEY (machine_id, name)
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

-- Meal-window prompts (spec §5d) — one row per settled window per day per machine.
-- 'yes'/'no' = answered for the day; 'deferred' = fire again next break.
CREATE TABLE IF NOT EXISTS meal_prompts (
    id               TEXT PRIMARY KEY,
    machine_id       TEXT NOT NULL,
    date             TEXT NOT NULL,
    window           TEXT NOT NULL,
    answered         TEXT NOT NULL,   -- 'yes' | 'no' | 'deferred'
    extended_minutes REAL              -- set only when answered = 'no'
);
CREATE INDEX IF NOT EXISTS idx_meal_prompts_day
    ON meal_prompts (machine_id, date, window);

-- Training break log (§5b, §9). Each completed/skipped training break gets a row.
CREATE TABLE IF NOT EXISTS breaks (
    id          TEXT PRIMARY KEY,
    machine_id  TEXT NOT NULL,
    ts          REAL NOT NULL,
    day         TEXT NOT NULL,
    layer       TEXT NOT NULL,   -- 'light' | 'training' | 'big'
    enforcement TEXT NOT NULL,   -- 'corner_countdown' | 'session_card' | 'hard_lock' | 'honor'
    outcome     TEXT NOT NULL,   -- 'completed' | 'skipped'
    duration_s  REAL
);
CREATE INDEX IF NOT EXISTS idx_breaks_day ON breaks (machine_id, day, layer);

-- Per-exercise progression (L1/L2/L3 — §5b, §9).
CREATE TABLE IF NOT EXISTS exercise_progress (
    machine_id   TEXT NOT NULL,
    exercise_id  TEXT NOT NULL,
    level        INTEGER NOT NULL DEFAULT 1,
    clean_streak INTEGER NOT NULL DEFAULT 0,
    consec_skips INTEGER NOT NULL DEFAULT 0,
    pain_until   TEXT,   -- ISO date; NULL = not on pain cooldown
    PRIMARY KEY (machine_id, exercise_id)
);

-- All user-facing settings live here (§8: config.yaml is machine plumbing only).
-- Values are JSON-encoded strings, decoded by pulse.settings.
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
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

    # --- meta key/value store --------------------------------------------------

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row is not None else default

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self._conn.commit()

    def get_useful_check_ms(self) -> float:
        v = self.get_meta("useful_check_ms")
        return float(v) if v is not None else 0.0

    def save_useful_check_ms(self, ms: float) -> None:
        self.set_meta("useful_check_ms", str(float(ms)))

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

    def checkins_with_dimension(self, dim: str) -> int:
        """Non-skipped check-ins where the given dimension column is non-NULL."""
        safe = {"block_type": "block_type", "energy": "energy", "note": "note"}.get(dim)
        if safe is None:
            return 0
        return self._conn.execute(
            f"SELECT COUNT(*) AS n FROM checkins "
            f"WHERE machine_id = ? AND skipped = 0 AND {safe} IS NOT NULL",
            (self.machine_id,),
        ).fetchone()["n"]

    def reflection_stage(self) -> int:
        """Stage 1 → 2 → 3 based on consistency thresholds (§7).
        Stage 2 unlocks after 5 non-skipped ratings on 3+ distinct days.
        Stage 3 unlocks after 5 additional check-ins with block_type filled."""
        if self.counted_checkins() < 5 or self.distinct_rating_days() < 3:
            return 1
        if self.checkins_with_dimension("block_type") < 5:
            return 2
        return 3

    def ratings_after_training(self, limit: int = 20) -> list[float]:
        """Ratings from check-ins that occurred within 2 hours of a completed training break."""
        rows = self._conn.execute(
            "SELECT c.rating FROM checkins c "
            "WHERE c.machine_id = ? AND c.skipped = 0 AND c.rating IS NOT NULL "
            "AND EXISTS ("
            "  SELECT 1 FROM breaks b "
            "  WHERE b.machine_id = c.machine_id "
            "  AND b.layer IN ('training', 'big') AND b.outcome = 'completed' "
            "  AND b.ts < c.ts AND b.ts > c.ts - 7200"
            ") "
            "ORDER BY c.ts DESC LIMIT ?",
            (self.machine_id, limit),
        ).fetchall()
        return [float(r["rating"]) for r in rows]

    def update_checkin_context(
        self, checkin_id: str, block_type: str | None, note: str | None
    ) -> None:
        """Attach block_type / note to an existing checkin row (Stage 2/3 context step)."""
        with self._lock:
            self._conn.execute(
                "UPDATE checkins SET block_type = ?, note = ? WHERE id = ? AND machine_id = ?",
                (block_type, note, checkin_id, self.machine_id),
            )
            self._conn.commit()

    def avg_rating_by_block_type(self) -> dict[str, float]:
        """Average rating per block_type; only groups with ≥ 3 entries (§7 cross-pattern)."""
        rows = self._conn.execute(
            "SELECT block_type, AVG(CAST(rating AS REAL)) AS avg_r, COUNT(*) AS n "
            "FROM checkins WHERE machine_id = ? AND skipped = 0 "
            "AND rating IS NOT NULL AND block_type IS NOT NULL "
            "GROUP BY block_type HAVING n >= 3 ORDER BY avg_r DESC",
            (self.machine_id,),
        ).fetchall()
        return {r["block_type"]: round(r["avg_r"], 1) for r in rows}

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

    # --- meal prompts (spec §5d) -----------------------------------------------

    def meal_settled_today(self, window_name: str, date: str | None = None) -> bool:
        """True if the window has a final (yes/no) answer today on this machine.
        A 'deferred' record does not count — the window can fire again next break."""
        d = date or _today_iso()
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM meal_prompts "
            "WHERE machine_id = ? AND date = ? AND window = ? AND answered IN ('yes', 'no')",
            (self.machine_id, d, window_name),
        ).fetchone()
        return row["n"] > 0

    def record_meal_prompt(
        self,
        window_name: str,
        answered: str,
        extended_minutes: float | None = None,
        ts: float | None = None,
    ) -> str:
        """Store the outcome of a meal-window prompt. Returns the new UUID."""
        mid = str(uuid.uuid4())
        ts = time.time() if ts is None else ts
        d = _date.fromtimestamp(ts).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO meal_prompts "
                "(id, machine_id, date, window, answered, extended_minutes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (mid, self.machine_id, d, window_name, answered, extended_minutes),
            )
            self._conn.commit()
        return mid

    # --- settings (raw JSON strings; pulse.settings owns the encoding) ----------

    def get_setting(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row is not None else None

    def set_setting(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self._conn.commit()

    def all_settings(self) -> dict[str, str]:
        return {
            r["key"]: r["value"]
            for r in self._conn.execute("SELECT key, value FROM settings").fetchall()
        }

    # --- breaks (training log) -------------------------------------------------

    def record_break(
        self,
        layer: str,
        enforcement: str,
        outcome: str,
        duration_s: float | None = None,
        ts: float | None = None,
    ) -> str:
        mid = str(uuid.uuid4())
        ts = time.time() if ts is None else ts
        d = _date.fromtimestamp(ts).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO breaks (id, machine_id, ts, day, layer, enforcement, outcome, duration_s) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (mid, self.machine_id, ts, d, layer, enforcement, outcome, duration_s),
            )
            self._conn.commit()
        return mid

    def training_count_today(self, day: str | None = None) -> int:
        """Number of completed training or big breaks today — counts toward the cap."""
        d = day or _today_iso()
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM breaks "
            "WHERE machine_id = ? AND day = ? AND layer IN ('training', 'big') "
            "AND outcome = 'completed'",
            (self.machine_id, d),
        ).fetchone()
        return row["n"]

    # --- exercise progression --------------------------------------------------

    def exercise_level(self, exercise_id: str) -> int:
        """Current level (1/2/3) for an exercise, creating a row at L1 if missing."""
        row = self._conn.execute(
            "SELECT level FROM exercise_progress WHERE machine_id = ? AND exercise_id = ?",
            (self.machine_id, exercise_id),
        ).fetchone()
        if row is None:
            with self._lock:
                self._conn.execute(
                    "INSERT OR IGNORE INTO exercise_progress "
                    "(machine_id, exercise_id, level, clean_streak, consec_skips) "
                    "VALUES (?, ?, 1, 0, 0)",
                    (self.machine_id, exercise_id),
                )
                self._conn.commit()
            return 1
        return row["level"]

    def record_exercise_done(self, exercise_id: str) -> dict:
        """Record a clean completion. Auto-promotes after 6 consecutive completions.
        Returns ``{level_changed: bool, new_level: int}``."""
        with self._lock:
            row = self._conn.execute(
                "SELECT level, clean_streak FROM exercise_progress "
                "WHERE machine_id = ? AND exercise_id = ?",
                (self.machine_id, exercise_id),
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO exercise_progress "
                    "(machine_id, exercise_id, level, clean_streak, consec_skips) "
                    "VALUES (?, ?, 1, 1, 0)",
                    (self.machine_id, exercise_id),
                )
                self._conn.commit()
                return {"level_changed": False, "new_level": 1}

            new_streak = row["clean_streak"] + 1
            new_level = row["level"]
            level_changed = False
            if new_streak >= 6 and new_level < 3:
                new_level += 1
                new_streak = 0
                level_changed = True

            self._conn.execute(
                "UPDATE exercise_progress "
                "SET level = ?, clean_streak = ?, consec_skips = 0 "
                "WHERE machine_id = ? AND exercise_id = ?",
                (new_level, new_streak, self.machine_id, exercise_id),
            )
            self._conn.commit()
        return {"level_changed": level_changed, "new_level": new_level}

    def record_exercise_skip(self, exercise_id: str) -> dict:
        """Record a skip. Auto-deloads after 2 consecutive skips (no shame messaging).
        Returns ``{level_changed: bool, new_level: int}``."""
        with self._lock:
            row = self._conn.execute(
                "SELECT level, consec_skips FROM exercise_progress "
                "WHERE machine_id = ? AND exercise_id = ?",
                (self.machine_id, exercise_id),
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO exercise_progress "
                    "(machine_id, exercise_id, level, clean_streak, consec_skips) "
                    "VALUES (?, ?, 1, 0, 1)",
                    (self.machine_id, exercise_id),
                )
                self._conn.commit()
                return {"level_changed": False, "new_level": 1}

            new_skips = row["consec_skips"] + 1
            new_level = row["level"]
            level_changed = False
            if new_skips >= 2 and new_level > 1:
                new_level -= 1
                new_skips = 0
                level_changed = True

            self._conn.execute(
                "UPDATE exercise_progress "
                "SET level = ?, clean_streak = 0, consec_skips = ? "
                "WHERE machine_id = ? AND exercise_id = ?",
                (new_level, new_skips, self.machine_id, exercise_id),
            )
            self._conn.commit()
        return {"level_changed": level_changed, "new_level": new_level}

    def record_exercise_pain(self, exercise_id: str, days: int = 7) -> None:
        """Flag pain — removes this exercise from rotation for `days` days."""
        from datetime import date as _d2, timedelta
        pain_until = (_d2.today() + timedelta(days=days)).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO exercise_progress "
                "(machine_id, exercise_id, level, clean_streak, consec_skips, pain_until) "
                "VALUES (?, ?, 1, 0, 1, ?) "
                "ON CONFLICT(machine_id, exercise_id) DO UPDATE SET "
                "pain_until = excluded.pain_until, consec_skips = consec_skips + 1",
                (self.machine_id, exercise_id, pain_until),
            )
            self._conn.commit()

    def is_pain_cooldown(self, exercise_id: str) -> bool:
        from datetime import date as _d2
        row = self._conn.execute(
            "SELECT pain_until FROM exercise_progress "
            "WHERE machine_id = ? AND exercise_id = ?",
            (self.machine_id, exercise_id),
        ).fetchone()
        if row is None or row["pain_until"] is None:
            return False
        return row["pain_until"] >= _d2.today().isoformat()

    # --- lifecycle -------------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            self._conn.close()
