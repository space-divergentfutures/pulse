"""Accumulator math (spec §4): active accrues, idle pauses, away resets, sleep never counts."""

from __future__ import annotations

from pulse.presence import PresenceState
from pulse.state_machine import EngineEvent

from conftest import IDLE_ACTIVE, IDLE_AWAY, IDLE_IDLE


def test_first_tick_is_baseline_only(make_driver, fast_config):
    driver = make_driver(fast_config)
    events = driver.poll(IDLE_ACTIVE)  # first tick establishes the baseline
    assert events == []
    assert driver.engine.snapshot().short_break_seconds == 0.0


def test_active_time_accumulates(make_driver, fast_config):
    driver = make_driver(fast_config, step_ms=5_000)
    driver.run(25.0, IDLE_ACTIVE)  # 25s of active work
    snap = driver.engine.snapshot()
    assert snap.presence is PresenceState.ACTIVE
    # One 5s step is the baseline, so ~20s accrues; allow one-step tolerance.
    assert 15.0 <= snap.short_break_seconds <= 25.0


def test_idle_pauses_without_resetting(make_driver, fast_config):
    driver = make_driver(fast_config)
    driver.run(20.0, IDLE_ACTIVE)
    before = driver.engine.snapshot().short_break_seconds
    assert before > 0

    events = driver.run(30.0, IDLE_IDLE)  # paused, but not long enough to be AWAY
    snap = driver.engine.snapshot()
    assert snap.presence is PresenceState.IDLE
    assert EngineEvent.AWAY_RESET not in events
    assert snap.short_break_seconds == before  # frozen, not reset, not grown


def test_away_resets_short_accumulator(make_driver, fast_config):
    driver = make_driver(fast_config)
    driver.run(20.0, IDLE_ACTIVE)
    assert driver.engine.snapshot().short_break_seconds > 0

    events = driver.poll(IDLE_AWAY)  # crossed the away threshold
    snap = driver.engine.snapshot()
    assert snap.presence is PresenceState.AWAY
    assert EngineEvent.AWAY_RESET in events
    assert snap.short_break_seconds == 0.0


def test_locked_is_treated_as_away(make_driver, fast_config):
    driver = make_driver(fast_config)
    driver.run(20.0, IDLE_ACTIVE)
    events = driver.poll(IDLE_ACTIVE, locked=True)  # active input but session locked
    snap = driver.engine.snapshot()
    assert snap.presence is PresenceState.LOCKED
    assert EngineEvent.AWAY_RESET in events
    assert snap.short_break_seconds == 0.0


def test_suspend_gap_never_counts_as_active(make_driver, fast_config):
    """A laptop-lid nap must never be counted as work (§4)."""
    driver = make_driver(fast_config)
    driver.run(20.0, IDLE_ACTIVE)
    before_lifetime = driver.engine.snapshot().lifetime_active_seconds

    # 45s gap: beyond the 30s suspend threshold but under the 120s away_reset.
    events = driver.jump(45.0, idle_seconds=IDLE_ACTIVE)
    snap = driver.engine.snapshot()
    assert snap.lifetime_active_seconds == before_lifetime  # the gap added nothing
    assert EngineEvent.AWAY_RESET not in events  # too short to be a real break
    assert snap.short_break_seconds > 0  # short cycle not reset by a brief gap


def test_long_suspend_gap_resets_short_cycle(make_driver, fast_config):
    driver = make_driver(fast_config)
    driver.run(20.0, IDLE_ACTIVE)
    assert driver.engine.snapshot().short_break_seconds > 0

    # 200s gap: beyond the 120s away_reset — a real break.
    events = driver.jump(200.0)
    snap = driver.engine.snapshot()
    assert EngineEvent.AWAY_RESET in events
    assert snap.short_break_seconds == 0.0


def test_useful_check_carries_remainder_across_threshold(make_driver, fast_config):
    """The 5.5-active-hour counter subtracts the threshold, never zeroes — it persists
    across days (§7). Here the fast threshold is 180s."""
    driver = make_driver(fast_config)
    events = driver.run(200.0, IDLE_ACTIVE)
    assert EngineEvent.USEFUL_CHECK_DUE in events
    # remainder ~ (200 - one baseline step) - 180 should be a small positive carry
    assert 0.0 <= driver.engine.snapshot().useful_check_seconds < 30.0
