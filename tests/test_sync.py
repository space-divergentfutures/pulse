"""Tests for Step 12: optional PocketBase sync (spec §12).

Covers: storage sync methods, SyncClient (mocked urllib), PocketBaseSync
push/pull logic, MachineConfig YAML loading, and the sync_enabled setting.
"""

from __future__ import annotations

import io
import json
import threading
import time
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pulse.machine_config import MachineConfig
from pulse.settings import SETTING_DEFS, Settings
from pulse.storage import PulseStorage
from pulse.sync import PocketBaseSync, SyncClient, _is_duplicate_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def storage(tmp_path):
    s = PulseStorage(tmp_path / "pulse.db")
    yield s
    s.close()


@pytest.fixture
def settings(tmp_path):
    s = PulseStorage(tmp_path / "settings.db")
    yield Settings(s)
    s.close()


# ---------------------------------------------------------------------------
# sync_log table + unsynced_* / record_synced / insert_remote_*
# ---------------------------------------------------------------------------

def test_sync_log_table_exists(storage):
    cur = storage._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_log'"
    )
    assert cur.fetchone() is not None


def test_unsynced_checkins_returns_new_rows(storage):
    cid = storage.add_checkin(7, ts=time.time())
    rows = storage.unsynced_checkins()
    assert len(rows) == 1
    assert rows[0]["id"] == cid


def test_unsynced_checkins_excludes_synced_rows(storage):
    cid = storage.add_checkin(7, ts=time.time())
    storage.record_synced(cid, "checkins")
    assert storage.unsynced_checkins() == []


def test_unsynced_checkins_honours_limit(storage):
    for _ in range(5):
        storage.add_checkin(5, ts=time.time())
    assert len(storage.unsynced_checkins(limit=2)) == 2


def test_unsynced_breaks_returns_new_rows(storage):
    bid = storage.record_break("light", "corner_countdown", "completed", ts=time.time())
    rows = storage.unsynced_breaks()
    assert len(rows) == 1
    assert rows[0]["id"] == bid


def test_unsynced_breaks_excludes_synced_rows(storage):
    bid = storage.record_break("light", "corner_countdown", "completed", ts=time.time())
    storage.record_synced(bid, "breaks")
    assert storage.unsynced_breaks() == []


def test_record_synced_idempotent(storage):
    cid = storage.add_checkin(8, ts=time.time())
    storage.record_synced(cid, "checkins")
    storage.record_synced(cid, "checkins")  # second call should not raise
    assert storage.unsynced_checkins() == []


def test_record_synced_scoped_to_collection(storage):
    cid = storage.add_checkin(8, ts=time.time())
    storage.record_synced(cid, "breaks")  # wrong collection
    assert len(storage.unsynced_checkins()) == 1  # still unsynced for checkins


def test_insert_remote_checkin_adds_new_row(storage):
    remote = {
        "id": "remote-uuid-1",
        "machine_id": "other-machine",
        "ts": time.time(),
        "day": "2026-07-08",
        "rating": 6,
        "block_type": None,
        "energy": None,
        "note": None,
        "skipped": 0,
    }
    inserted = storage.insert_remote_checkin(remote)
    assert inserted is True
    rows = storage._conn.execute(
        "SELECT id FROM checkins WHERE id = 'remote-uuid-1'"
    ).fetchall()
    assert len(rows) == 1


def test_insert_remote_checkin_returns_false_on_duplicate(storage):
    remote = {
        "id": "remote-uuid-2",
        "machine_id": "other-machine",
        "ts": time.time(),
        "day": "2026-07-08",
        "rating": 5,
        "block_type": None,
        "energy": None,
        "note": None,
        "skipped": 0,
    }
    storage.insert_remote_checkin(remote)
    second = storage.insert_remote_checkin(remote)
    assert second is False


def test_insert_remote_checkin_does_not_overwrite_local(storage):
    cid = storage.add_checkin(9, ts=time.time())
    row = storage._conn.execute("SELECT * FROM checkins WHERE id=?", (cid,)).fetchone()
    # Try inserting the same id from a "remote" source with a different rating.
    remote = dict(row)
    remote["rating"] = 1
    storage.insert_remote_checkin(remote)
    updated = storage._conn.execute(
        "SELECT rating FROM checkins WHERE id=?", (cid,)
    ).fetchone()
    assert updated["rating"] == 9  # unchanged


def test_insert_remote_break_adds_new_row(storage):
    remote = {
        "id": "remote-break-1",
        "machine_id": "other-machine",
        "ts": time.time(),
        "day": "2026-07-08",
        "layer": "light",
        "enforcement": "corner_countdown",
        "outcome": "completed",
        "duration_s": None,
    }
    inserted = storage.insert_remote_break(remote)
    assert inserted is True


def test_insert_remote_break_returns_false_on_duplicate(storage):
    remote = {
        "id": "remote-break-2",
        "machine_id": "other-machine",
        "ts": time.time(),
        "day": "2026-07-08",
        "layer": "light",
        "enforcement": "corner_countdown",
        "outcome": "completed",
        "duration_s": 90.0,
    }
    storage.insert_remote_break(remote)
    assert storage.insert_remote_break(remote) is False


# ---------------------------------------------------------------------------
# _is_duplicate_id helper
# ---------------------------------------------------------------------------

def test_is_duplicate_id_detects_id_key():
    assert _is_duplicate_id({"data": {"id": "some error"}}) is True


def test_is_duplicate_id_detects_unique_text():
    assert _is_duplicate_id({"message": "value not unique"}) is True


def test_is_duplicate_id_detects_already_text():
    assert _is_duplicate_id({"message": "record already exists"}) is True


def test_is_duplicate_id_false_on_unrelated_body():
    assert _is_duplicate_id({"message": "some other validation error"}) is False


# ---------------------------------------------------------------------------
# SyncClient — mocked urllib
# ---------------------------------------------------------------------------

def _fake_urlopen_ctx(status: int, body: dict | None = None):
    """Return a context-manager mock that yields a response with given status."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = json.dumps(body or {}).encode()
    resp.__enter__ = lambda s: resp
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _http_error(code: int, body: dict | None = None) -> urllib.error.HTTPError:
    body_bytes = json.dumps(body or {}).encode()
    return urllib.error.HTTPError(
        url="", code=code, msg="", hdrs={}, fp=io.BytesIO(body_bytes)
    )


def test_sync_client_create_returns_true_on_201():
    with patch("urllib.request.urlopen", return_value=_fake_urlopen_ctx(201)):
        client = SyncClient("http://100.1.2.3:8090", "token123")
        assert client.create("checkins", {"id": "abc"}) is True


def test_sync_client_create_returns_true_on_200():
    with patch("urllib.request.urlopen", return_value=_fake_urlopen_ctx(200)):
        client = SyncClient("http://100.1.2.3:8090", "token123")
        assert client.create("checkins", {"id": "abc"}) is True


def test_sync_client_create_returns_true_on_duplicate_400():
    err = _http_error(400, {"data": {"id": "not unique"}})
    with patch("urllib.request.urlopen", side_effect=err):
        client = SyncClient("http://100.1.2.3:8090", "token123")
        assert client.create("checkins", {"id": "abc"}) is True


def test_sync_client_create_returns_false_on_server_error():
    err = _http_error(500, {})
    with patch("urllib.request.urlopen", side_effect=err):
        client = SyncClient("http://100.1.2.3:8090", "token123")
        assert client.create("checkins", {"id": "abc"}) is False


def test_sync_client_create_returns_false_on_connection_error():
    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        client = SyncClient("http://100.1.2.3:8090", "token123")
        assert client.create("checkins", {"id": "abc"}) is False


def test_sync_client_list_remote_returns_items():
    items = [{"id": "r1", "machine_id": "other"}]
    body = {"items": items}
    with patch("urllib.request.urlopen", return_value=_fake_urlopen_ctx(200, body)):
        client = SyncClient("http://100.1.2.3:8090", "token123")
        result = client.list_remote("checkins", skip_machine_id="my-machine")
    assert result == items


def test_sync_client_list_remote_returns_empty_on_error():
    with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
        client = SyncClient("http://100.1.2.3:8090", "token123")
        result = client.list_remote("checkins", skip_machine_id="my-machine")
    assert result == []


def test_sync_client_sends_auth_header():
    captured = {}

    def _urlopen(req, timeout=None):
        captured["auth"] = req.get_header("Authorization")
        return _fake_urlopen_ctx(201)

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        client = SyncClient("http://100.1.2.3:8090", "supersecret")
        client.create("checkins", {"id": "x"})

    assert captured["auth"] == "Bearer supersecret"


# ---------------------------------------------------------------------------
# PocketBaseSync push/pull logic
# ---------------------------------------------------------------------------

class _FakeClient:
    """Fake SyncClient for PocketBaseSync tests — no HTTP."""

    def __init__(self, *, create_ok=True, list_by_collection=None):
        self._create_ok = create_ok
        self._list = list_by_collection or {}
        self.created: list[tuple[str, dict]] = []

    def create(self, collection: str, data: dict) -> bool:
        self.created.append((collection, data))
        return self._create_ok

    def list_remote(self, collection: str, skip_machine_id: str, **_) -> list[dict]:
        return self._list.get(collection, [])


def test_sync_once_pushes_checkins(storage):
    storage.add_checkin(7, ts=time.time())
    client = _FakeClient()
    syncer = PocketBaseSync(storage, client)
    stats = syncer.sync_once()
    assert stats["pushed"] >= 1
    assert any(coll == "checkins" for coll, _ in client.created)


def test_sync_once_marks_synced_on_success(storage):
    storage.add_checkin(7, ts=time.time())
    syncer = PocketBaseSync(storage, _FakeClient())
    syncer.sync_once()
    assert storage.unsynced_checkins() == []


def test_sync_once_does_not_remark_already_synced(storage):
    storage.add_checkin(7, ts=time.time())
    client = _FakeClient()
    syncer = PocketBaseSync(storage, client)
    syncer.sync_once()
    first_count = len(client.created)
    syncer.sync_once()
    assert len(client.created) == first_count  # nothing new to push


def test_sync_once_leaves_unsent_on_failure(storage):
    storage.add_checkin(5, ts=time.time())
    syncer = PocketBaseSync(storage, _FakeClient(create_ok=False))
    stats = syncer.sync_once()
    assert stats["errors"] == 1
    assert len(storage.unsynced_checkins()) == 1  # still unsent — retried next cycle


def test_sync_once_pushes_breaks(storage):
    storage.record_break("light", "corner_countdown", "completed", ts=time.time())
    client = _FakeClient()
    syncer = PocketBaseSync(storage, client)
    syncer.sync_once()
    assert any(coll == "breaks" for coll, _ in client.created)


def test_sync_once_pulls_remote_checkins(storage):
    mid = storage.machine_id
    remote = {
        "id": "remote-cid",
        "machine_id": "other-machine",
        "ts": time.time(),
        "day": "2026-07-08",
        "rating": 8,
        "block_type": None,
        "energy": None,
        "note": None,
        "skipped": 0,
    }
    client = _FakeClient(list_by_collection={"checkins": [remote], "breaks": []})
    syncer = PocketBaseSync(storage, client)
    stats = syncer.sync_once()
    assert stats["pulled"] >= 1
    row = storage._conn.execute(
        "SELECT id FROM checkins WHERE id='remote-cid'"
    ).fetchone()
    assert row is not None


def test_sync_once_pulls_remote_breaks(storage):
    remote = {
        "id": "remote-bid",
        "machine_id": "other-machine",
        "ts": time.time(),
        "day": "2026-07-08",
        "layer": "light",
        "enforcement": "corner_countdown",
        "outcome": "completed",
        "duration_s": None,
    }
    client = _FakeClient(list_by_collection={"checkins": [], "breaks": [remote]})
    syncer = PocketBaseSync(storage, client)
    stats = syncer.sync_once()
    assert stats["pulled"] >= 1


def test_sync_once_returns_stats_dict(storage):
    stats = PocketBaseSync(storage, _FakeClient()).sync_once()
    assert "pushed" in stats and "pulled" in stats and "errors" in stats


# ---------------------------------------------------------------------------
# PocketBaseSync background thread lifecycle
# ---------------------------------------------------------------------------

def test_pocketbase_sync_start_spawns_daemon_thread(storage):
    client = _FakeClient()
    syncer = PocketBaseSync(storage, client)
    # Don't wait for the 30-second startup delay; just check the thread is alive.
    syncer.start(interval_seconds=9999)
    assert syncer._thread is not None
    assert syncer._thread.daemon is True
    assert syncer._thread.is_alive()
    syncer.stop()


def test_pocketbase_sync_stop_sets_event(storage):
    syncer = PocketBaseSync(storage, _FakeClient())
    syncer.start(interval_seconds=9999)
    syncer.stop()
    assert syncer._stop.is_set()


def test_pocketbase_sync_start_idempotent(storage):
    syncer = PocketBaseSync(storage, _FakeClient())
    syncer.start(interval_seconds=9999)
    first_thread = syncer._thread
    syncer.start(interval_seconds=9999)  # should not spawn a second thread
    assert syncer._thread is first_thread
    syncer.stop()


# ---------------------------------------------------------------------------
# MachineConfig
# ---------------------------------------------------------------------------

def test_machine_config_defaults_when_no_file(tmp_path):
    mc = MachineConfig.load(tmp_path / "nonexistent.yaml")
    assert mc.db_path is None
    assert mc.sync_url is None
    assert mc.machine_name is None


def test_machine_config_loads_sync_url(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("sync_url: http://100.1.2.3:8090\n", encoding="utf-8")
    mc = MachineConfig.load(cfg)
    assert mc.sync_url == "http://100.1.2.3:8090"


def test_machine_config_loads_db_path(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("db_path: /data/pulse.db\n", encoding="utf-8")
    mc = MachineConfig.load(cfg)
    assert mc.db_path == "/data/pulse.db"


def test_machine_config_loads_machine_name(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("machine_name: my-laptop\n", encoding="utf-8")
    mc = MachineConfig.load(cfg)
    assert mc.machine_name == "my-laptop"


def test_machine_config_empty_string_becomes_none(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("sync_url: ''\nmachine_name: ''\n", encoding="utf-8")
    mc = MachineConfig.load(cfg)
    assert mc.sync_url is None
    assert mc.machine_name is None


def test_machine_config_missing_keys_are_none(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("machine_name: desktop\n", encoding="utf-8")
    mc = MachineConfig.load(cfg)
    assert mc.sync_url is None
    assert mc.db_path is None


def test_machine_config_corrupt_yaml_returns_defaults(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(": : invalid yaml :::\n", encoding="utf-8")
    mc = MachineConfig.load(cfg)
    assert mc.sync_url is None


# ---------------------------------------------------------------------------
# sync_enabled setting
# ---------------------------------------------------------------------------

def test_sync_enabled_setting_exists():
    by_key = {d.key: d for d in SETTING_DEFS}
    assert "sync_enabled" in by_key


def test_sync_enabled_default_false():
    by_key = {d.key: d for d in SETTING_DEFS}
    assert by_key["sync_enabled"].default is False


def test_sync_enabled_is_bool():
    by_key = {d.key: d for d in SETTING_DEFS}
    assert by_key["sync_enabled"].kind == "bool"


def test_sync_enabled_group_is_sync():
    by_key = {d.key: d for d in SETTING_DEFS}
    assert by_key["sync_enabled"].group == "Sync"


def test_sync_enabled_has_full_explainer():
    by_key = {d.key: d for d in SETTING_DEFS}
    d = by_key["sync_enabled"]
    assert d.explainer.what and d.explainer.who and d.explainer.tradeoff


def test_sync_enabled_readable_via_settings(settings):
    assert settings.get("sync_enabled") is False


def test_sync_enabled_settable(settings):
    settings.set("sync_enabled", True)
    assert settings.get("sync_enabled") is True


def test_setting_count_with_sync():
    # 12 (step 5) + 1 (focus_mode) + 4 (appearance) + 1 (start_with_windows) + 1 (sync_enabled) = 19
    assert len(SETTING_DEFS) == 19
