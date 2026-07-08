"""Tests for Focus Guard (spec §5c): focus mode setting + routing invariants."""

from __future__ import annotations

import pytest

from pulse.settings import SETTING_DEFS, Settings
from pulse.storage import PulseStorage


@pytest.fixture
def settings(tmp_path):
    s = PulseStorage(tmp_path / "pulse.db")
    yield Settings(s)
    s.close()


# ---------------------------------------------------------------------------
# Setting definition
# ---------------------------------------------------------------------------

def test_focus_mode_enabled_default_false(settings):
    assert settings.get("focus_mode_enabled") is False


def test_focus_mode_enabled_set_true(settings):
    settings.set("focus_mode_enabled", True)
    assert settings.get("focus_mode_enabled") is True


def test_focus_mode_enabled_set_false(settings):
    settings.set("focus_mode_enabled", True)
    settings.set("focus_mode_enabled", False)
    assert settings.get("focus_mode_enabled") is False


def test_focus_mode_validation_rejects_non_bool(settings):
    with pytest.raises(ValueError):
        settings.set("focus_mode_enabled", "yes")


def test_focus_mode_setting_has_full_explainer():
    by_key = {d.key: d for d in SETTING_DEFS}
    d = by_key["focus_mode_enabled"]
    assert d.explainer.what and d.explainer.who and d.explainer.tradeoff


def test_focus_mode_setting_group():
    by_key = {d.key: d for d in SETTING_DEFS}
    assert by_key["focus_mode_enabled"].group == "Focus Guard"


def test_focus_mode_is_bool_kind():
    by_key = {d.key: d for d in SETTING_DEFS}
    assert by_key["focus_mode_enabled"].kind == "bool"


def test_setting_count_includes_focus_guard():
    # 12 (step 5) + 1 (focus_mode) + 4 (appearance) + 1 (start_with_windows) = 18
    assert len(SETTING_DEFS) == 18


# ---------------------------------------------------------------------------
# All-settings explainer completeness (regression: new setting must comply)
# ---------------------------------------------------------------------------

def test_every_setting_still_has_full_explainer():
    for d in SETTING_DEFS:
        assert d.explainer.what, f"{d.key}: missing 'what'"
        assert d.explainer.who,  f"{d.key}: missing 'who'"
        assert d.explainer.tradeoff, f"{d.key}: missing 'tradeoff'"
