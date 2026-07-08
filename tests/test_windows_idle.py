"""Wrap-safe idle math (spec §4): the 32-bit tick counter wraps at ~49.7 days.

These tests target the pure helper so the wrap can be exercised without waiting 49 days
or being on Windows-specific hardware. compute_idle_ms lives in the Windows adapter but
is import-safe to test here (the module only touches ctypes at call time)."""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows platform adapter"
)

TICK_MODULUS = 1 << 32


def _compute():
    from pulse.platform.windows import compute_idle_ms

    return compute_idle_ms


def test_normal_case_no_wrap():
    compute_idle_ms = _compute()
    # last input 10s ago, no wrap
    assert compute_idle_ms(1_000_000, 990_000) == 10_000


def test_zero_idle():
    compute_idle_ms = _compute()
    assert compute_idle_ms(500_000, 500_000) == 0


def test_wrap_boundary_gives_positive_elapsed():
    compute_idle_ms = _compute()
    # last input was 100ms before the 32-bit counter wrapped; now is 50ms after wrap.
    last_input = TICK_MODULUS - 100
    now = 50
    # Naive subtraction would be hugely negative; modular arithmetic gives 150ms.
    assert compute_idle_ms(now, last_input) == 150


def test_result_always_in_range():
    compute_idle_ms = _compute()
    for now, last in [(0, TICK_MODULUS - 1), (123, 456), (TICK_MODULUS - 1, 0)]:
        result = compute_idle_ms(now, last)
        assert 0 <= result < TICK_MODULUS
