"""Settings persistence, profiles, and config derivation (spec §6)."""

from __future__ import annotations

import pytest

from pulse.settings import PROFILE_BY_KEY, SETTING_DEFS, Settings
from pulse.storage import PulseStorage


@pytest.fixture
def settings(tmp_path):
    s = PulseStorage(tmp_path / "pulse.db")
    yield Settings(s)
    s.close()


def test_defaults_returned_when_unset(settings):
    assert settings.get("light_interval_minutes") == 30.0
    assert settings.get("enforcement_light") == "corner_countdown"
    assert settings.get("tracking_enabled") is True


def test_set_get_roundtrip_persists(settings):
    settings.set("light_interval_minutes", 22.0)
    settings.set("enforcement_light", "soft_overlay")
    assert settings.get("light_interval_minutes") == 22.0
    assert settings.get("enforcement_light") == "soft_overlay"


def test_validation_rejects_bad_values(settings):
    with pytest.raises(ValueError):
        settings.set("enforcement_light", "not_a_style")
    with pytest.raises(ValueError):
        settings.set("light_interval_minutes", 999.0)  # above max
    with pytest.raises(ValueError):
        settings.set("tracking_enabled", "yes")  # not a bool
    with pytest.raises(KeyError):
        settings.set("nonexistent", 1)


def test_every_setting_has_a_full_explainer(settings):
    # §6: every setting must explain what / who / trade-off, non-optional.
    for d in SETTING_DEFS:
        assert d.explainer.what and d.explainer.who and d.explainer.tradeoff


def test_apply_profile_sets_overrides_and_records_active(settings):
    settings.apply_profile("frequent_gentle")
    assert settings.active_profile == "frequent_gentle"
    assert settings.get("light_interval_minutes") == 20.0
    assert settings.get("enforcement_light") == "soft_overlay"


def test_minimal_profile_turns_off_training_and_tracking(settings):
    settings.apply_profile("minimal_movement")
    assert settings.get("training_enabled") is False
    assert settings.get("tracking_enabled") is False


def test_first_run_flag(settings):
    assert settings.first_run_complete is False
    settings.mark_first_run_complete()
    assert settings.first_run_complete is True


def test_to_timing_config_reflects_settings(settings):
    settings.set("light_interval_minutes", 25.0)
    settings.set("warning_lead_minutes", 4.0)
    cfg = settings.to_timing_config()
    assert cfg.light_interval_minutes == 25.0
    assert cfg.warning_lead_minutes == 4.0


def test_to_timing_config_clamps_impossible_warning_lead(settings):
    # A hand-edited lead >= interval must not crash the engine.
    settings.set("light_interval_minutes", 10.0)
    settings.set("warning_lead_minutes", 15.0)
    cfg = settings.to_timing_config()  # would raise if unclamped
    assert cfg.warning_lead_minutes < cfg.light_interval_minutes


def test_all_profiles_apply_cleanly(settings):
    # Every profile's overrides must be valid settings that derive a usable config.
    for key in PROFILE_BY_KEY:
        settings.apply_profile(key)
        cfg = settings.to_timing_config()
        assert cfg.warning_lead_minutes < cfg.light_interval_minutes
