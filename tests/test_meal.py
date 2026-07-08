"""Tests for meal-window detection and storage (spec §5d)."""

from datetime import time

import pytest

from pulse.meal import DEFAULT_WINDOWS, MealWindow, active_window_now
from pulse.storage import PulseStorage


# ---------------------------------------------------------------------------
# active_window_now — time-injection tests (no real clock)
# ---------------------------------------------------------------------------

def test_inside_lunch_window():
    assert active_window_now(_now=time(12, 0)) == "lunch"

def test_before_lunch_window():
    assert active_window_now(_now=time(11, 0)) is None

def test_after_lunch_window():
    assert active_window_now(_now=time(14, 30)) is None

def test_at_start_boundary():
    # 11:30 is inclusive
    assert active_window_now(_now=time(11, 30)) == "lunch"

def test_at_end_boundary():
    # lunch + 2.5h = 14:00, inclusive
    assert active_window_now(_now=time(14, 0)) == "lunch"
    assert active_window_now(_now=time(14, 1)) is None

def test_custom_window():
    windows = (MealWindow("dinner", "18:00", 1.5),)
    assert active_window_now(windows, _now=time(18, 30)) == "dinner"
    assert active_window_now(windows, _now=time(17, 59)) is None
    assert active_window_now(windows, _now=time(19, 31)) is None


# ---------------------------------------------------------------------------
# storage.meal_settled_today / record_meal_prompt
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    return PulseStorage(str(tmp_path / "meal_test.db"))


def test_not_settled_initially(store):
    assert not store.meal_settled_today("lunch")

def test_yes_settles(store):
    store.record_meal_prompt("lunch", "yes")
    assert store.meal_settled_today("lunch")

def test_no_settles_with_duration(store):
    store.record_meal_prompt("lunch", "no", 20.0)
    assert store.meal_settled_today("lunch")

def test_deferred_does_not_settle(store):
    store.record_meal_prompt("lunch", "deferred")
    assert not store.meal_settled_today("lunch")

def test_different_windows_independent(store):
    store.record_meal_prompt("lunch", "yes")
    assert not store.meal_settled_today("dinner")

def test_deferred_then_yes_settles(store):
    store.record_meal_prompt("lunch", "deferred")
    assert not store.meal_settled_today("lunch")
    store.record_meal_prompt("lunch", "yes")
    assert store.meal_settled_today("lunch")
