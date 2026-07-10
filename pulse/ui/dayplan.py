"""Day plan card controller (reading feature).

A small corner card shown once at the first active moment of each day: "how long
are you at the desk today?" The answer (or a skip) goes to the app via callback;
the app decides whether a reading session fits and schedules it. Same modest
bottom-right placement as the break card — never a screen takeover.
"""

from __future__ import annotations

from collections.abc import Callable

import webview

from ..platform.base import PlatformInterface
from . import WEB_DIR

_DAYPLAN_HTML = WEB_DIR / "dayplan.html"

DEFAULT_WIDTH = 320
DEFAULT_HEIGHT = 300
DEFAULT_MARGIN = 12


class _DayPlanBridge:
    def __init__(self, card: "DayPlanCard") -> None:
        self._card = card

    def plan_day(self, hours: float) -> dict:
        cb = self._card._on_planned
        if cb:
            cb(float(hours))
        return {"ok": True}

    def skip_day_plan(self) -> dict:
        cb = self._card._on_planned
        if cb:
            cb(None)
        return {"ok": True}

    def ready(self) -> dict:
        self._card._ready = True
        return {"ok": True}


class DayPlanCard:
    def __init__(
        self,
        platform: PlatformInterface,
        *,
        on_planned: Callable[[float | None], None] | None = None,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        margin: int = DEFAULT_MARGIN,
    ) -> None:
        self._platform = platform
        self._on_planned = on_planned
        self._width = width
        self._height = height
        self._margin = margin
        self._window = None
        self._ready = False

    def create(self):
        x, y = self._corner_position()
        self._window = webview.create_window(
            "PULSE — your day",
            url=str(_DAYPLAN_HTML),
            js_api=_DayPlanBridge(self),
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
            hidden=True,  # shown once per day when the ask fires
        )
        return self._window

    def _corner_position(self) -> tuple[int, int]:
        left, top, right, bottom = self._platform.get_work_area()
        return right - self._width - self._margin, bottom - self._height - self._margin

    def ask(self, default_hours: float = 4.0) -> None:
        """Reset the picker and show the card."""
        self._eval(f"window.pulse.reset({float(default_hours)})")
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
