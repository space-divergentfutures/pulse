"""Shared test fixtures — a fully mocked clock (spec §12).

The engine never reads a real clock: the caller supplies ``now_ms`` to every ``tick``.
``EngineDriver`` is that caller under test control — it advances a virtual monotonic
clock and polls the engine on a fixed cadence, exactly like the production run loop
will, so active/idle/away/suspend behaviour is deterministic and instant.
"""

from __future__ import annotations

import pytest

from pulse.config import TimingConfig
from pulse.state_machine import EngineEvent, SessionEngine

# Idle-second stand-ins for each presence class, given the configs below
# (active < 60s; away_reset is minutes*60). Callers pass these to make intent obvious.
IDLE_ACTIVE = 1.0     # actively typing/moving
IDLE_IDLE = 80.0      # paused: >= 60s but < away_reset (fast_config away_reset = 120s)
IDLE_AWAY = 200.0     # stepped away: >= away_reset


@pytest.fixture
def fast_config() -> TimingConfig:
    """Small intervals so timing tests run instantly but exercise identical logic.

    light interval 60s (warn at 30s), away_reset 120s, boundary 180s,
    useful-check 180s (0.05h), suspend gap 30s.
    """
    return TimingConfig(
        light_interval_minutes=1.0,
        warning_lead_minutes=0.5,
        away_reset_minutes=2.0,
        boundary_interval_minutes=3.0,
        useful_check_hours=0.05,
        suspend_gap_seconds=30.0,
    )


class EngineDriver:
    """Drives a SessionEngine off a virtual clock at a fixed poll cadence."""

    def __init__(self, engine: SessionEngine, step_ms: int = 5_000) -> None:
        self.engine = engine
        self.step_ms = step_ms
        self.now_ms = 0

    def poll(self, idle_seconds: float, locked: bool = False) -> list[EngineEvent]:
        """One poll, advancing the clock by the normal cadence step."""
        self.now_ms += self.step_ms
        return self.engine.tick(self.now_ms, idle_seconds, locked)

    def run(self, seconds: float, idle_seconds: float, locked: bool = False) -> list[EngineEvent]:
        """Poll repeatedly for ``seconds`` of virtual time at the cadence step."""
        collected: list[EngineEvent] = []
        elapsed = 0
        target = int(seconds * 1000)
        while elapsed < target:
            collected += self.poll(idle_seconds, locked)
            elapsed += self.step_ms
        return collected

    def jump(self, gap_seconds: float, idle_seconds: float = IDLE_ACTIVE, locked: bool = False) -> list[EngineEvent]:
        """A single poll after a large clock jump — simulates sleep/hibernate/suspend."""
        self.now_ms += int(gap_seconds * 1000)
        return self.engine.tick(self.now_ms, idle_seconds, locked)


@pytest.fixture
def make_driver():
    def _make(config: TimingConfig, step_ms: int = 5_000) -> EngineDriver:
        return EngineDriver(SessionEngine(config), step_ms=step_ms)

    return _make
