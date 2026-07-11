"""Local data export (post-Step-13) — CSV / JSON of the reflection tables.

The mirror's data belongs to the person looking into it (§13): everything PULSE
stores can be taken away as plain files, any time, with one click. The export is
local-only — the user picks a folder, files are written there, nothing is sent
anywhere. A manifest README rides along explaining every column and restating
the privacy floor, so the files stand on their own.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .storage import PulseStorage

# Order matters only for the manifest listing.
EXPORT_TABLES: tuple[str, ...] = (
    "checkins", "breaks", "meal_prompts", "active_time", "day_plans"
)

# Tables whose ts column is epoch seconds get a derived human-readable ts_iso
# column in the export — raw epoch floats are useless in a spreadsheet.
_EPOCH_TS_TABLES = {"checkins", "breaks"}


def export_data(
    storage: "PulseStorage",
    output_dir: Path | str,
    fmt: Literal["csv", "json"] = "csv",
    days: int | None = None,
) -> list[Path]:
    """Export the reflection tables to ``output_dir`` as CSV or JSON files.

    ``days`` limits the export to the last N days (None/0 = everything).
    Returns the list of data files written (the manifest is extra). Tables with
    no rows in range are skipped — no empty files.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    written: list[Path] = []

    for table in EXPORT_TABLES:
        rows = storage.fetch_table(table, days=days)
        if not rows:
            continue
        if table in _EPOCH_TS_TABLES:
            rows = [_with_ts_iso(r) for r in rows]

        path = output_dir / f"pulse_{table}_{stamp}.{fmt}"
        if fmt == "csv":
            _write_csv(path, rows)
        else:
            _write_json(path, rows)
        written.append(path)

    if written:
        _write_manifest(output_dir, written, fmt, days)
    return written


def _with_ts_iso(row: dict[str, Any]) -> dict[str, Any]:
    """Insert a human-readable ts_iso right after the raw epoch ts."""
    out: dict[str, Any] = {}
    for key, value in row.items():
        out[key] = value
        if key == "ts" and isinstance(value, (int, float)):
            out["ts_iso"] = datetime.fromtimestamp(value).isoformat(timespec="seconds")
    return out


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False, default=str)


def _write_manifest(
    output_dir: Path, files: list[Path], fmt: str, days: int | None
) -> None:
    scope = f"Last {days} days only" if days else "All available data"
    file_list = "\n".join(f"  - {p.name}" for p in files)
    content = f"""PULSE personal data export
Generated: {datetime.now().isoformat(timespec="seconds")}
Format: {fmt.upper()}
Scope: {scope}

Files in this export:
{file_list}

---------------------------------------------------------------
PRIVACY & OWNERSHIP
---------------------------------------------------------------
These files were created locally on your computer. Nothing was
sent to any server, cloud, or third party.

PULSE only ever stores:
- your self-reported block ratings and the optional context you
  chose to add (block type, energy, free-text notes)
- break timing and outcomes (light / training / big)
- meal-window answers and the food/water chips you selected
- daily totals of accumulated active minutes
- your day-plan answers and whether the reading session happened

PULSE never stores window titles, app names, keystrokes,
screenshots, or any diagnostic/clinical labels.

This data belongs to you — use it for personal analysis, backup,
or migration to another tool.

---------------------------------------------------------------
COLUMN REFERENCE
---------------------------------------------------------------

checkins — one row per post-break check-in
  id            unique row id (UUID)
  machine_id    which of your machines wrote the row
  ts            timestamp, epoch seconds
  ts_iso        the same timestamp, human-readable (added at export)
  day           date (YYYY-MM-DD)
  rating        your block rating (empty if skipped)
  block_type    optional context you chose
  energy        optional energy level
  note          optional free-text note
  skipped       1 if you skipped rating that block, else 0

breaks — one row per completed/skipped training or big break
  id, machine_id, ts, ts_iso, day   as above
  layer         "light", "training", or "big"
  enforcement   the style in force ("corner_countdown",
                "session_card", "hard_lock", or "honor")
  outcome       "completed" or "skipped"
  duration_s    duration in seconds, when recorded

meal_prompts — one row per meal-window answer
  id, machine_id                    as above
  date          the calendar date of the window
  window        which meal window (e.g. "lunch")
  answered      "yes", "no", or "deferred"
  extended_minutes  length of the food break, when you chose one
  food_detail   "light" / "medium" / "heavy", if you answered
  water_amount  "little" / "glass" / "plenty", if you answered

active_time — one row per machine per day
  machine_id, day                   as above
  active_minutes    total active minutes accumulated that day

day_plans — one row per sitting (wake-to-sleep, not a calendar day) you were
  asked the desk-time question in. The table name is historical.
  id, machine_id, date              as above (sitting start's local date)
  planned_hours     how long you said you'd be at the desk
                    (empty = you skipped the question)
  reading_at        when the reading session was scheduled
                    (epoch seconds; empty = no reading that sitting)
  reading_done      1 if you took the reading session, else 0
  ts                when the sitting started, epoch seconds
  started_ts        sitting start (first active moment); empty on rows from
                    before this column existed
  ended_ts          sitting end (last active moment before you left); empty
                    while the sitting is still open, or on old rows

---------------------------------------------------------------
TIPS
---------------------------------------------------------------
- CSV opens directly in Excel, Google Sheets, or LibreOffice.
- JSON is better for scripts or importing into another tool.
- Rows from different machines never collide: sum active_time
  across machine_id values for whole-day totals.
- These files are copies — deleting them does not touch PULSE's
  own database.
"""
    (output_dir / "PULSE_EXPORT_README.txt").write_text(content, encoding="utf-8")
