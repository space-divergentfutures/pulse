"""Tests for Step 11: tray icon, pause/resume, startup setting, quit (spec §11)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from pulse.settings import SETTING_DEFS, Settings
from pulse.storage import PulseStorage
from pulse.ui.tray import PulseTray, _make_icon


# ---------------------------------------------------------------------------
# Icon generation
# ---------------------------------------------------------------------------

def test_make_icon_returns_pil_image():
    img = _make_icon()
    assert isinstance(img, Image.Image)


def test_make_icon_size_is_64():
    img = _make_icon()
    assert img.size == (64, 64)


def test_make_icon_is_rgba():
    img = _make_icon()
    assert img.mode == "RGBA"


def test_make_icon_has_non_transparent_pixels():
    img = _make_icon()
    # A pixel inside the circle should be opaque
    _, _, _, a = img.getpixel((32, 32))
    assert a > 0


def test_make_icon_uses_teal_colour():
    img = _make_icon()
    # The teal ring (127, 209, 193) should appear somewhere in the image.
    # Sample the centre of the outer ring area (radius ~30px).
    r, g, b, _ = img.getpixel((32, 8))  # top of ring
    assert (r, g, b) == (127, 209, 193)


# ---------------------------------------------------------------------------
# PulseTray construction
# ---------------------------------------------------------------------------

def _make_tray(**overrides):
    defaults = dict(
        on_pause_resume=lambda: None,
        on_break_now=lambda: None,
        on_insights=lambda: None,
        on_settings=lambda: None,
        on_quit=lambda: None,
        get_today_count=lambda: 0,
        get_paused=lambda: False,
    )
    defaults.update(overrides)
    return PulseTray(**defaults)


def test_tray_constructs_without_error():
    tray = _make_tray()
    assert tray is not None


def test_tray_stop_noop_before_start():
    tray = _make_tray()
    tray.stop()  # should not raise


def test_tray_callbacks_stored():
    called = {}
    tray = _make_tray(
        on_pause_resume=lambda: called.setdefault("pause", True),
        on_quit=lambda: called.setdefault("quit", True),
    )
    tray._on_pause_resume()
    tray._on_quit()
    assert called.get("pause")
    assert called.get("quit")


def test_tray_get_today_count_callable():
    tray = _make_tray(get_today_count=lambda: 3)
    assert tray._get_today_count() == 3


def test_tray_get_paused_callable():
    state = {"paused": False}
    tray = _make_tray(get_paused=lambda: state["paused"])
    assert tray._get_paused() is False
    state["paused"] = True
    assert tray._get_paused() is True


# ---------------------------------------------------------------------------
# Tray start (mock pystray so no real icon is created)
# ---------------------------------------------------------------------------

def test_tray_start_creates_icon():
    tray = _make_tray()
    mock_icon = MagicMock()
    mock_menu = MagicMock()
    with patch("pulse.ui.tray.PulseTray._build_menu", return_value=mock_menu), \
         patch("pystray.Icon", return_value=mock_icon) as mock_icon_cls:
        tray.start()
    mock_icon_cls.assert_called_once()
    mock_icon.run.assert_called_once()  # called via threading.Thread.start → thread runs


def test_tray_start_spawns_daemon_thread():
    tray = _make_tray()
    with patch("pystray.Icon") as mock_icon_cls:
        mock_icon_cls.return_value = MagicMock()
        tray.start()
    assert tray._thread is not None
    assert tray._thread.daemon is True


def test_tray_stop_calls_icon_stop():
    tray = _make_tray()
    mock_icon = MagicMock()
    tray._icon = mock_icon
    tray.stop()
    mock_icon.stop.assert_called_once()


def test_tray_stop_swallows_exceptions():
    tray = _make_tray()
    mock_icon = MagicMock()
    mock_icon.stop.side_effect = RuntimeError("pystray boom")
    tray._icon = mock_icon
    tray.stop()  # should not propagate


# ---------------------------------------------------------------------------
# Tray menu (mock pystray.Menu + MenuItem)
# ---------------------------------------------------------------------------

def test_tray_build_menu_returns_something():
    tray = _make_tray()
    with patch("pystray.Menu") as mock_menu_cls, \
         patch("pystray.MenuItem"):
        mock_menu_cls.SEPARATOR = "---"
        tray._build_menu()
    mock_menu_cls.assert_called_once()


# ---------------------------------------------------------------------------
# start_with_windows setting
# ---------------------------------------------------------------------------

def test_start_with_windows_setting_exists():
    by_key = {d.key: d for d in SETTING_DEFS}
    assert "start_with_windows" in by_key


def test_start_with_windows_default_false():
    by_key = {d.key: d for d in SETTING_DEFS}
    assert by_key["start_with_windows"].default is False


def test_start_with_windows_is_bool():
    by_key = {d.key: d for d in SETTING_DEFS}
    assert by_key["start_with_windows"].kind == "bool"


def test_start_with_windows_group_system():
    by_key = {d.key: d for d in SETTING_DEFS}
    assert by_key["start_with_windows"].group == "System"


def test_start_with_windows_has_full_explainer():
    by_key = {d.key: d for d in SETTING_DEFS}
    d = by_key["start_with_windows"]
    assert d.explainer.what and d.explainer.who and d.explainer.tradeoff


@pytest.fixture
def settings(tmp_path):
    s = PulseStorage(tmp_path / "pulse.db")
    yield Settings(s)
    s.close()


def test_start_with_windows_readable_via_settings(settings):
    assert settings.get("start_with_windows") is False


def test_start_with_windows_settable(settings):
    settings.set("start_with_windows", True)
    assert settings.get("start_with_windows") is True


# ---------------------------------------------------------------------------
# _startup_command + _sync_startup_key (unit-level, no real registry)
# ---------------------------------------------------------------------------

def test_startup_command_empty_in_development():
    from pulse.app import _startup_command
    import sys
    # In the test environment sys.frozen is not set → should return ""
    assert not getattr(sys, "frozen", False)
    assert _startup_command() == ""


def test_sync_startup_key_skips_when_no_command():
    from pulse.app import _sync_startup_key
    mock_platform = MagicMock()
    mock_settings = MagicMock()
    mock_settings.get.return_value = True  # enabled
    _sync_startup_key(mock_platform, mock_settings)
    # No command (development) → set_startup_enabled should NOT be called with True
    mock_platform.set_startup_enabled.assert_not_called()


def test_sync_startup_key_disables_when_false(tmp_path):
    from pulse.app import _sync_startup_key
    mock_platform = MagicMock()
    mock_settings = MagicMock()
    mock_settings.get.return_value = False  # disabled
    _sync_startup_key(mock_platform, mock_settings)
    mock_platform.set_startup_enabled.assert_called_once_with(False)


def test_sync_startup_key_swallows_registry_exceptions(tmp_path):
    from pulse.app import _sync_startup_key
    mock_platform = MagicMock()
    mock_platform.set_startup_enabled.side_effect = OSError("registry locked")
    mock_settings = MagicMock()
    mock_settings.get.return_value = False
    _sync_startup_key(mock_platform, mock_settings)  # should not raise
