"""Light-layer state machine (spec §5a): work → warn → break → work, events fire once."""

from __future__ import annotations

from pulse.state_machine import EngineEvent, SessionState

from conftest import IDLE_ACTIVE, IDLE_AWAY


def test_warning_then_break_due_in_order(make_driver, fast_config):
    driver = make_driver(fast_config)
    # fast_config: warn at 30s active, break due at 60s active.
    warn_events = driver.run(40.0, IDLE_ACTIVE)
    assert EngineEvent.WARNING_START in warn_events
    assert EngineEvent.BREAK_DUE not in warn_events
    assert driver.engine.session_state is SessionState.WARN

    due_events = driver.run(30.0, IDLE_ACTIVE)  # push past the 60s interval
    assert EngineEvent.BREAK_DUE in due_events


def test_warning_and_break_due_fire_exactly_once(make_driver, fast_config):
    driver = make_driver(fast_config)
    events = driver.run(180.0, IDLE_ACTIVE)  # keep working long past the mark
    assert events.count(EngineEvent.WARNING_START) == 1
    assert events.count(EngineEvent.BREAK_DUE) == 1


def test_self_started_break_resets_cycle(make_driver, fast_config):
    driver = make_driver(fast_config)
    driver.run(70.0, IDLE_ACTIVE)  # past the interval
    assert driver.engine.session_state is SessionState.WARN

    assert driver.engine.start_break() == [EngineEvent.BREAK_STARTED]
    assert driver.engine.session_state is SessionState.BREAK

    # While on the break, active input does NOT accrue toward the next break.
    before = driver.engine.snapshot().short_break_seconds
    driver.run(20.0, IDLE_ACTIVE)
    assert driver.engine.snapshot().short_break_seconds == before

    assert driver.engine.complete_break() == [EngineEvent.BREAK_COMPLETED]
    assert driver.engine.session_state is SessionState.WORK
    assert driver.engine.snapshot().short_break_seconds == 0.0


def test_away_rearms_the_warning(make_driver, fast_config):
    driver = make_driver(fast_config)
    driver.run(40.0, IDLE_ACTIVE)
    assert driver.engine.session_state is SessionState.WARN

    driver.poll(IDLE_AWAY)  # real break resets the cycle
    assert driver.engine.session_state is SessionState.WORK

    rearmed = driver.run(40.0, IDLE_ACTIVE)  # a fresh cycle must warn again
    assert EngineEvent.WARNING_START in rearmed


def test_boundary_due_fires_once_and_respects_daily_cap(make_driver, fast_config):
    driver = make_driver(fast_config)  # boundary at 180s active
    events = driver.run(190.0, IDLE_ACTIVE)
    assert events.count(EngineEvent.BOUNDARY_DUE) == 1

    # After a training session the boundary re-arms.
    driver.engine.record_training_session()
    assert driver.engine.snapshot().boundary_seconds == 0.0


def test_boundary_suppressed_when_daily_cap_reached(make_driver, fast_config):
    driver = make_driver(fast_config)
    # Simulate the day's training sessions already done (default cap = 2).
    driver.engine.record_training_session()
    driver.engine.record_training_session()
    events = driver.run(190.0, IDLE_ACTIVE)
    assert EngineEvent.BOUNDARY_DUE not in events


def test_roll_day_resets_training_cap_not_lifetime(make_driver, fast_config):
    driver = make_driver(fast_config)
    driver.run(30.0, IDLE_ACTIVE)
    driver.engine.record_training_session()
    lifetime_before = driver.engine.snapshot().lifetime_active_seconds

    driver.engine.roll_day()
    snap = driver.engine.snapshot()
    assert snap.training_sessions_today == 0
    assert snap.lifetime_active_seconds == lifetime_before  # persists across the day
