"""Config invariants (spec §6 defaults)."""

from __future__ import annotations

import pytest

from pulse.config import TimingConfig


def test_defaults_match_spec():
    c = TimingConfig()
    assert c.light_interval_minutes == 30.0
    assert c.warning_lead_minutes == 5.0
    assert c.away_reset_minutes == 10.0
    assert c.max_training_sessions_per_day == 2
    assert c.useful_check_hours == 5.5
    assert c.insight_min_observations == 15


def test_warning_lead_must_be_under_interval():
    with pytest.raises(ValueError):
        TimingConfig(light_interval_minutes=5.0, warning_lead_minutes=5.0)


def test_positive_intervals_required():
    with pytest.raises(ValueError):
        TimingConfig(light_interval_minutes=0.0)
