"""Light break card controller (spec §5a, §5d).

A modest bottom-right card shown when a light break starts — movement suggestion,
hydration (rides on every break), and the self-started timer. Never a screen takeover;
the light layer is a gentle nudge, and doing/rating is honor-based.

When the break starts inside a meal window (§5d), the card shows the meal question
first ("have you eaten today?") and then transitions to the normal break content.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import webview

from ..platform.base import PlatformInterface
from . import WEB_DIR

_BREAK_HTML = WEB_DIR / "break_card.html"

DEFAULT_WIDTH = 320
# Outer height. The meal question phase needs ~264px client area; adding the ~39px
# WebView2 frameless chrome overhead gives 303px — rounded up to 320 for breathing room.
# Normal breaks comfortably fit in this height too.
DEFAULT_HEIGHT = 320
DEFAULT_MARGIN = 12


class _BreakBridge:
    def __init__(self, card: "BreakCard") -> None:
        self._card = card

    def done(self) -> dict:
        self._card._fire("done")
        return {"ok": True}

    def timer_finished(self) -> dict:
        self._card._fire("timer_finished")
        return {"ok": True}

    def meal_yes(self) -> dict:
        cb = self._card._on_meal_settled_cb
        if cb:
            cb(self._card._meal_window, "yes", None)
        return {"ok": True}

    def meal_no(self, minutes: float) -> dict:
        cb = self._card._on_meal_settled_cb
        if cb:
            cb(self._card._meal_window, "no", float(minutes))
        return {"ok": True}

    def meal_deferred(self) -> dict:
        cb = self._card._on_meal_settled_cb
        if cb:
            cb(self._card._meal_window, "deferred", None)
        return {"ok": True}

    def ready(self) -> dict:
        self._card._ready = True
        return {"ok": True}


class BreakCard:
    def __init__(
        self,
        platform: PlatformInterface,
        *,
        on_done: Callable[[], None] | None = None,
        on_timer_finished: Callable[[], None] | None = None,
        on_meal_settled: Callable[[str, str, float | None], None] | None = None,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        margin: int = DEFAULT_MARGIN,
    ) -> None:
        self._platform = platform
        self._width = width
        self._height = height
        self._margin = margin
        self._callbacks = {"done": on_done, "timer_finished": on_timer_finished}
        self._on_meal_settled_cb = on_meal_settled
        self._meal_window: str = ""  # set by start_break(); read in bridge callbacks
        self._window = None
        self._ready = False

    def create(self):
        x, y = self._corner_position()
        self._window = webview.create_window(
            "PULSE break",
            url=str(_BREAK_HTML),
            js_api=_BreakBridge(self),
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
            hidden=True,  # shown only when a break starts
        )
        return self._window

    def _corner_position(self) -> tuple[int, int]:
        left, top, right, bottom = self._platform.get_work_area()
        return right - self._width - self._margin, bottom - self._height - self._margin

    def start_break(
        self,
        *,
        name: str,
        detail: str,
        hydration: str,
        seconds: float,
        kicker: str = "Light break",
        honor: str = "move if you can — it's yours, do it your way",
        meal_prompt: bool = False,
        meal_window: str = "",
        meal_min_minutes: int = 10,
        meal_max_minutes: int = 45,
        meal_default_minutes: int = 20,
    ) -> None:
        self._meal_window = meal_window
        payload = json.dumps(
            {
                "kicker": kicker,
                "name": name,
                "detail": detail,
                "hydration": hydration,
                "honor": honor,
                "seconds": float(seconds),
                "mealPrompt": meal_prompt,
                "mealWindow": meal_window,
                "mealMin": meal_min_minutes,
                "mealMax": meal_max_minutes,
                "mealDefault": meal_default_minutes,
            }
        )
        self._eval(f"window.pulse.startBreak({payload})")
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

    def _fire(self, name: str) -> None:
        cb = self._callbacks.get(name)
        if cb is not None:
            cb()
