"""Tests for Step 13: packaging + WebView2 check (spec §11).

These tests verify:
- The __main__ entry point imports cleanly.
- check_webview2_or_warn returns True when the registry key exists.
- check_webview2_or_warn returns False (and shows a messagebox) when absent.
- check_webview2_or_warn returns True on non-Windows platforms.
- is_webview2_available is a pure boolean with no side effects.
- PULSE.spec, build.ps1, and installer/pulse.iss exist.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Root of the repo (tests/ is one level down).
_REPO = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def test_main_module_importable():
    """python -m pulse entry point must be importable without side effects."""
    import pulse.__main__  # noqa: F401 — just check the import works


def test_run_pulse_launcher_exists():
    """PyInstaller entry point (absolute imports, no relative package) must exist."""
    assert (_REPO / "run_pulse.py").exists()


def test_run_pulse_uses_absolute_import():
    """run_pulse.py must not use relative imports — they break in a frozen bundle."""
    src = (_REPO / "run_pulse.py").read_text(encoding="utf-8")
    assert "from pulse.app import" in src
    assert "from .app" not in src


def test_main_function_exists():
    from pulse.app import main
    assert callable(main)


# ---------------------------------------------------------------------------
# Build artefacts exist
# ---------------------------------------------------------------------------

def test_pyinstaller_spec_exists():
    assert (_REPO / "PULSE.spec").exists(), "PULSE.spec missing"


def test_build_script_exists():
    assert (_REPO / "build.ps1").exists(), "build.ps1 missing"


def test_inno_setup_script_exists():
    assert (_REPO / "installer" / "pulse.iss").exists(), "installer/pulse.iss missing"


def test_release_workflow_exists():
    assert (_REPO / ".github" / "workflows" / "release.yml").exists(), \
        ".github/workflows/release.yml missing"


def test_settings_docs_exist():
    assert (_REPO / "SETTINGS.md").exists(), "SETTINGS.md missing"


def test_config_example_exists():
    assert (_REPO / "config.example.yaml").exists(), "config.example.yaml missing"


# ---------------------------------------------------------------------------
# is_webview2_available
# ---------------------------------------------------------------------------

def test_is_webview2_available_returns_true_when_key_found():
    from pulse.platform.webview_check import is_webview2_available
    with patch("sys.platform", "win32"), \
         patch("winreg.OpenKey", return_value=MagicMock()):
        assert is_webview2_available() is True


def test_is_webview2_available_returns_false_when_all_keys_missing():
    from pulse.platform.webview_check import is_webview2_available
    with patch("sys.platform", "win32"), \
         patch("winreg.OpenKey", side_effect=OSError("not found")):
        assert is_webview2_available() is False


def test_is_webview2_available_returns_true_on_non_windows():
    from pulse.platform.webview_check import is_webview2_available
    with patch("sys.platform", "linux"):
        assert is_webview2_available() is True


def test_is_webview2_available_returns_true_on_darwin():
    from pulse.platform.webview_check import is_webview2_available
    with patch("sys.platform", "darwin"):
        assert is_webview2_available() is True


# ---------------------------------------------------------------------------
# check_webview2_or_warn
# ---------------------------------------------------------------------------

def test_check_webview2_or_warn_returns_true_when_available():
    from pulse.platform.webview_check import check_webview2_or_warn
    with patch("pulse.platform.webview_check.is_webview2_available", return_value=True):
        assert check_webview2_or_warn() is True


def test_check_webview2_or_warn_returns_false_and_shows_messagebox():
    from pulse.platform.webview_check import check_webview2_or_warn
    mock_mb = MagicMock(return_value=1)
    with patch("pulse.platform.webview_check.is_webview2_available", return_value=False), \
         patch("ctypes.windll", create=True) as mock_windll:
        mock_windll.user32.MessageBoxW = mock_mb
        result = check_webview2_or_warn()
    assert result is False
    mock_mb.assert_called_once()


def test_check_webview2_messagebox_mentions_webview2():
    from pulse.platform.webview_check import check_webview2_or_warn
    captured = {}
    def _fake_mb(hwnd, text, title, flags):
        captured["text"] = text
        captured["title"] = title
        return 1
    with patch("pulse.platform.webview_check.is_webview2_available", return_value=False), \
         patch("ctypes.windll", create=True) as mock_windll:
        mock_windll.user32.MessageBoxW = _fake_mb
        check_webview2_or_warn()
    assert "WebView2" in captured.get("text", "")
    assert "PULSE" in captured.get("title", "")


# ---------------------------------------------------------------------------
# PULSE.spec content sanity
# ---------------------------------------------------------------------------

def test_spec_references_main_entry_point():
    spec = (_REPO / "PULSE.spec").read_text(encoding="utf-8")
    assert "run_pulse.py" in spec


def test_spec_includes_web_assets():
    spec = (_REPO / "PULSE.spec").read_text(encoding="utf-8")
    assert "pulse/ui/web" in spec


def test_spec_is_windowed():
    spec = (_REPO / "PULSE.spec").read_text(encoding="utf-8")
    # console=False means no terminal window
    assert "console=False" in spec


# ---------------------------------------------------------------------------
# Inno Setup script content sanity
# ---------------------------------------------------------------------------

def test_iss_references_pyinstaller_output():
    iss = (_REPO / "installer" / "pulse.iss").read_text(encoding="utf-8")
    assert r"dist\PULSE" in iss


def test_iss_checks_webview2():
    iss = (_REPO / "installer" / "pulse.iss").read_text(encoding="utf-8")
    assert "WebView2" in iss or "WV2" in iss


def test_iss_low_privilege():
    iss = (_REPO / "installer" / "pulse.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in iss


# ---------------------------------------------------------------------------
# README content
# ---------------------------------------------------------------------------

def test_readme_mentions_smartscreen():
    readme = (_REPO / "README.md").read_text(encoding="utf-8")
    assert "SmartScreen" in readme or "More info" in readme


def test_readme_mentions_wayland_caveat():
    readme = (_REPO / "README.md").read_text(encoding="utf-8")
    assert "Wayland" in readme


def test_readme_has_non_diagnostic_stance():
    readme = (_REPO / "README.md").read_text(encoding="utf-8")
    assert "not medical advice" in readme.lower() or "non-diagnostic" in readme.lower() \
        or "does not diagnose" in readme.lower()


def test_readme_has_privacy_section():
    readme = (_REPO / "README.md").read_text(encoding="utf-8")
    assert "Privacy" in readme
