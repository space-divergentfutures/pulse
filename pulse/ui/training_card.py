"""Training session card controller (spec §5b).

A frameless, always-on-top, centered panel that runs the full training session:
  get-ready (90 s countdown) → exercises one-by-one → completion screen
  OR → Big Break option picker → 12-min timer

Enforcement modes (§6, set via Python callbacks):
  session_card (default): Skip button visible, honor-based — the session expects
    commitment, but no OS tricks are used to hold you there.
  hard_lock: Skip button hidden via the hardLock flag in the JS payload; the
    window is still technically escapable (Ctrl+Alt+Del) — per spec, that's fine;
    it works because the user *chose* it.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import webview

from ..platform.base import PlatformInterface
from . import WEB_DIR

_CARD_HTML = WEB_DIR / "training_card.html"

DEFAULT_WIDTH  = 420
DEFAULT_HEIGHT = 480


class _TrainingBridge:
    def __init__(self, card: "TrainingCard") -> None:
        self._card = card

    def ready(self) -> dict:
        self._card._ready = True
        return {"ok": True}

    def exercise_done(self, exercise_id: str) -> dict:
        result = self._card._on_exercise_outcome_cb(exercise_id, "done")
        return result or {"ok": True, "level_changed": False, "new_level": 1}

    def exercise_skip(self, exercise_id: str) -> dict:
        result = self._card._on_exercise_outcome_cb(exercise_id, "skip")
        return result or {"ok": True, "level_changed": False, "new_level": 1}

    def exercise_pain(self, exercise_id: str) -> dict:
        result = self._card._on_exercise_outcome_cb(exercise_id, "pain")
        return result or {"ok": True, "level_changed": False, "new_level": 1}

    def session_complete(self, outcomes_json: str) -> dict:
        try:
            outcomes = json.loads(outcomes_json)
        except (json.JSONDecodeError, TypeError):
            outcomes = []
        self._card._on_session_complete_cb(outcomes)
        return {"ok": True}

    def close_card(self) -> dict:
        self._card._on_close_cb()
        return {"ok": True}

    def big_break_started(self, option_id: str) -> dict:
        return {"ok": True}

    def big_break_done(self) -> dict:
        self._card._on_big_break_done_cb()
        return {"ok": True}


class TrainingCard:
    def __init__(
        self,
        platform: PlatformInterface,
        *,
        on_exercise_outcome: Callable[[str, str], dict],
        on_session_complete: Callable[[list], None],
        on_close: Callable[[], None],
        on_big_break_done: Callable[[], None],
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
    ) -> None:
        self._platform = platform
        self._on_exercise_outcome_cb = on_exercise_outcome
        self._on_session_complete_cb = on_session_complete
        self._on_close_cb = on_close
        self._on_big_break_done_cb = on_big_break_done
        self._width = width
        self._height = height
        self._window = None
        self._ready = False

    def create(self):
        x, y = self._centered_position()
        self._window = webview.create_window(
            "PULSE — Training",
            url=str(_CARD_HTML),
            js_api=_TrainingBridge(self),
            width=self._width,
            height=self._height,
            x=x,
            y=y,
            frameless=True,
            on_top=True,
            resizable=False,
            transparent=False,
            background_color="#12141a",
            easy_drag=False,
            hidden=True,
        )
        return self._window

    def _centered_position(self) -> tuple[int, int]:
        left, top, right, bottom = self._platform.get_work_area()
        cx = (left + right) // 2
        cy = (top + bottom) // 2
        return cx - self._width // 2, cy - self._height // 2

    def start_session(self, payload: dict) -> None:
        self._eval(f"window.pulse.startSession({json.dumps(payload)})")
        self.show()

    def show(self) -> None:
        if self._window is not None:
            self._window.show()

    def hide(self) -> None:
        if self._window is not None:
            self._window.hide()

    def destroy(self) -> None:
        if self._window is not None:
            self._window.destroy()

    def _eval(self, js: str) -> None:
        if self._window is not None:
            self._window.evaluate_js(js)
