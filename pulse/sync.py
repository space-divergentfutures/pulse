"""Optional PocketBase sync module (spec §12).

Off by default. Enabled via the sync_enabled setting + a base URL in config.yaml +
PULSE_PB_TOKEN in the environment. Local SQLite is ALWAYS the source of truth; sync
is best-effort and additive (never destructive).

The implicit retry queue: any row absent from sync_log is retried on the next cycle.

Required PocketBase collection schemas
--------------------------------------
checkins:  id (text, custom UUID), machine_id (text), ts (number), day (text),
           rating (number, nullable), block_type (text, nullable),
           energy (number, nullable), note (text, nullable), skipped (bool)

breaks:    id (text, custom UUID), machine_id (text), ts (number), day (text),
           layer (text), enforcement (text), outcome (text), duration_s (number, nullable)

Security notes
--------------
- base URL must be a Tailscale address — NEVER expose PocketBase on the public internet.
- Token is read from PULSE_PB_TOKEN env var ONLY — never stored in any file.
- machine_id is a UUID; it is safe to interpolate in the PocketBase filter expression.
"""

from __future__ import annotations

import json as _json
import logging
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .storage import PulseStorage

_log = logging.getLogger(__name__)


def _make_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _is_duplicate_id(body: dict) -> bool:
    """Heuristic: PocketBase 400 response when id already exists."""
    try:
        data = body.get("data", {})
        if "id" in data:
            return True
        body_str = str(body).lower()
        return "already" in body_str or "unique" in body_str
    except Exception:
        return False


class SyncClient:
    """Thin urllib wrapper for the PocketBase REST API.

    Uses Python's built-in urllib so no extra runtime dependency is needed.
    All calls are synchronous with a short timeout — they run on the sync
    background thread, never on the pywebview main thread.
    """

    def __init__(self, base_url: str, token: str, timeout: float = 5.0) -> None:
        self._base = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout

    def create(self, collection: str, data: dict) -> bool:
        """POST a record. Returns True if created or if the id is already present.
        Returns False on transient network or server errors (will retry next cycle)."""
        url = f"{self._base}/api/collections/{collection}/records"
        body = _json.dumps(data).encode()
        req = urllib.request.Request(
            url, data=body, headers=_make_headers(self._token), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return resp.status in (200, 201)
        except urllib.error.HTTPError as exc:
            if exc.code == 400:
                try:
                    body_data = _json.loads(exc.read().decode())
                    if _is_duplicate_id(body_data):
                        return True  # already synced in a prior run — count as success
                except Exception:
                    pass
            _log.warning("sync create %s id=%s: HTTP %d", collection, data.get("id"), exc.code)
            return False
        except Exception as exc:
            _log.debug("sync create %s: %s", collection, exc)
            return False

    def list_remote(
        self, collection: str, skip_machine_id: str, page_size: int = 200
    ) -> list[dict]:
        """Fetch records from machines other than skip_machine_id.
        Returns [] on any error — pull is best-effort."""
        # machine_id is a UUID (alphanumeric + hyphens) — safe to interpolate.
        filter_expr = urllib.parse.quote(f"machine_id != '{skip_machine_id}'")
        url = (
            f"{self._base}/api/collections/{collection}/records"
            f"?filter={filter_expr}&perPage={page_size}&page=1"
        )
        req = urllib.request.Request(url, headers=_make_headers(self._token))
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = _json.loads(resp.read())
                return data.get("items", [])
        except Exception as exc:
            _log.debug("sync list_remote %s: %s", collection, exc)
        return []


class PocketBaseSync:
    """Orchestrates push/pull between local SQLite and a PocketBase instance.

    Push: any row absent from sync_log is sent to PocketBase. On success the row
          is recorded in sync_log so it is skipped next time. On failure it is
          silently left out of sync_log and retried on the next cycle.

    Pull: records from other machine_ids are fetched and inserted locally with
          ON CONFLICT IGNORE — local rows are never overwritten by remote data.

    Background thread: starts 30 s after app launch (let the UI settle first),
    then runs every ``interval_seconds`` (default 5 min).
    """

    def __init__(self, storage: "PulseStorage", client: SyncClient) -> None:
        self._storage = storage
        self._client = client
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # --- public ---------------------------------------------------------------

    def start(self, interval_seconds: float = 300.0) -> None:
        """Start the background sync thread. Idempotent."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(interval_seconds,),
            daemon=True,
            name="pulse-sync",
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the background thread to stop. Does not join — returns immediately."""
        self._stop.set()

    def sync_once(self) -> dict:
        """One push + pull pass. Returns {pushed, pulled, errors}."""
        pushed = pulled = errors = 0
        mid = self._storage.machine_id

        for row in self._storage.unsynced_checkins():
            if self._client.create("checkins", row):
                self._storage.record_synced(row["id"], "checkins")
                pushed += 1
            else:
                errors += 1

        for row in self._storage.unsynced_breaks():
            if self._client.create("breaks", row):
                self._storage.record_synced(row["id"], "breaks")
                pushed += 1
            else:
                errors += 1

        for remote in self._client.list_remote("checkins", skip_machine_id=mid):
            if self._storage.insert_remote_checkin(remote):
                pulled += 1

        for remote in self._client.list_remote("breaks", skip_machine_id=mid):
            if self._storage.insert_remote_break(remote):
                pulled += 1

        _log.info("sync: pushed=%d pulled=%d errors=%d", pushed, pulled, errors)
        return {"pushed": pushed, "pulled": pulled, "errors": errors}

    # --- background thread ----------------------------------------------------

    def _run(self, interval_seconds: float) -> None:
        self._stop.wait(30)  # startup delay — let the UI and storage settle first
        if not self._stop.is_set():
            self._safe_sync()
        while not self._stop.wait(interval_seconds):
            self._safe_sync()

    def _safe_sync(self) -> None:
        try:
            self.sync_once()
        except Exception:
            _log.exception("sync_once raised unexpectedly")
