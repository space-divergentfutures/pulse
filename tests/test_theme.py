"""Tests for the appearance theme system (pulse/theme.py)."""

from __future__ import annotations

import pytest

from pulse.settings import SETTING_DEFS, Settings
from pulse.storage import PulseStorage
from pulse.theme import (
    ACCENT_PRESETS,
    FONT_FAMILIES,
    FONT_SIZE_ZOOM,
    THEME_PALETTES,
    build_vars,
    inject_theme,
)


@pytest.fixture
def settings(tmp_path):
    s = PulseStorage(tmp_path / "pulse.db")
    yield Settings(s)
    s.close()


# ---------------------------------------------------------------------------
# Preset catalogue completeness
# ---------------------------------------------------------------------------

def test_all_accent_presets_present():
    expected = {"teal", "violet", "coral", "sky", "sage", "peach", "lavender"}
    assert set(ACCENT_PRESETS.keys()) == expected


def test_all_accent_presets_have_required_vars():
    required = {"--accent", "--accent-btn", "--accent-btn-hi", "--done"}
    for name, preset in ACCENT_PRESETS.items():
        assert required <= set(preset.keys()), f"{name} is missing vars"


def test_all_theme_palettes_present():
    assert set(THEME_PALETTES.keys()) == {"dark", "light", "dark_hc", "light_hc"}


def test_all_theme_palettes_have_required_vars():
    required = {"--bg", "--card-a", "--card-b", "--ink", "--muted", "--warn"}
    for name, pal in THEME_PALETTES.items():
        assert required <= set(pal.keys()), f"{name} is missing vars"


def test_font_families_present():
    assert set(FONT_FAMILIES.keys()) == {"default", "mono", "serif"}


def test_font_size_zoom_values_are_floats():
    for k, v in FONT_SIZE_ZOOM.items():
        assert isinstance(v, float), f"{k} zoom is not a float"
    assert FONT_SIZE_ZOOM["normal"] == 1.0


# ---------------------------------------------------------------------------
# build_vars: defaults and overrides
# ---------------------------------------------------------------------------

def test_build_vars_defaults(settings):
    v = build_vars(settings)
    assert "--accent" in v
    assert "--bg" in v
    assert "--font-family" in v
    assert "--ui-zoom" in v
    assert v["--ui-zoom"] == "1.0"  # normal zoom


def test_build_vars_accent_override(settings):
    settings.set("appearance_accent", "violet")
    v = build_vars(settings)
    assert v["--accent"] == ACCENT_PRESETS["violet"]["--accent"]


def test_build_vars_theme_override(settings):
    settings.set("appearance_theme", "light")
    v = build_vars(settings)
    assert v["--bg"] == THEME_PALETTES["light"]["--bg"]
    assert v["--ink"] == THEME_PALETTES["light"]["--ink"]


def test_build_vars_font_size(settings):
    settings.set("appearance_font_size", "xlarge")
    v = build_vars(settings)
    assert v["--ui-zoom"] == str(FONT_SIZE_ZOOM["xlarge"])


def test_build_vars_font_mono(settings):
    settings.set("appearance_font", "mono")
    v = build_vars(settings)
    assert "Consolas" in v["--font-family"]


def test_build_vars_dark_hc(settings):
    settings.set("appearance_theme", "dark_hc")
    v = build_vars(settings)
    assert v["--bg"] == "#000000"
    assert v["--ink"] == "#ffffff"


# ---------------------------------------------------------------------------
# inject_theme: smoke test with mock window
# ---------------------------------------------------------------------------

class _MockWindow:
    def __init__(self):
        self.last_js = None

    def evaluate_js(self, js):
        self.last_js = js


def test_inject_theme_calls_evaluate_js(settings):
    win = _MockWindow()
    v = build_vars(settings)
    inject_theme(win, v)
    assert win.last_js is not None
    assert "_pt" in win.last_js
    assert ":root" in win.last_js


def test_inject_theme_includes_accent_value(settings):
    settings.set("appearance_accent", "coral")
    win = _MockWindow()
    v = build_vars(settings)
    inject_theme(win, v)
    assert ACCENT_PRESETS["coral"]["--accent"] in win.last_js


# ---------------------------------------------------------------------------
# Settings definitions
# ---------------------------------------------------------------------------

def test_appearance_settings_have_full_explainers():
    appearance_keys = {
        "appearance_theme", "appearance_accent",
        "appearance_font_size", "appearance_font",
    }
    by_key = {d.key: d for d in SETTING_DEFS}
    for key in appearance_keys:
        d = by_key[key]
        assert d.explainer.what and d.explainer.who and d.explainer.tradeoff, key


def test_appearance_settings_in_appearance_group():
    by_key = {d.key: d for d in SETTING_DEFS}
    for key in ("appearance_theme", "appearance_accent", "appearance_font_size", "appearance_font"):
        assert by_key[key].group == "Appearance", key


def test_appearance_defaults():
    by_key = {d.key: d for d in SETTING_DEFS}
    assert by_key["appearance_theme"].default == "dark"
    assert by_key["appearance_accent"].default == "teal"
    assert by_key["appearance_font_size"].default == "normal"
    assert by_key["appearance_font"].default == "default"


def test_setting_count_with_appearance():
    # 12 (step 5) + 1 (focus_mode) + 4 (appearance) + 1 (start_with_windows) + 1 (sync_enabled) = 19
    assert len(SETTING_DEFS) == 23


