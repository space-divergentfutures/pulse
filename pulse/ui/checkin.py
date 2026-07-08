"""Check-in + graph controller (spec §7).

Stage 1: one question, one tap — "How did that block go?" — then the graph immediately.
The rating rides on the break you're already taking (one interruption, not two). The
bridge's rate()/skip() return the fresh graph payload straight back to the page, so the
feedback is instant — that immediacy is the reward loop (§7).
"""

from __future__ import annotations

from collections.abc import Callable

import webview

from ..platform.base import PlatformInterface
from . import WEB_DIR

_CHECKIN_HTML = WEB_DIR / "checkin.html"

DEFAULT_WIDTH = 360
DEFAULT_HEIGHT = 344
DEFAULT_MARGIN = 12


class _CheckinBridge:
    def __init__(self, card: "CheckinCard") -> None:
        self._card = card

    def rate(self, value: int) -> dict:
        return self._card._on_rating(int(value), False)

    def skip(self) -> dict:
        return self._card._on_rating(None, True)

    def close(self) -> dict:
        self._card._on_close_cb()
        return {"ok": True}

    def ready(self) -> dict:
        self._card._ready = True
        return {"ok": True}


class CheckinCard:
    def __init__(
        self,
        platform: PlatformInterface,
        *,
        on_rating: Callable[[int | None, bool], dict],
        on_close: Callable[[], None],
        scale_max: int = 10,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        margin: int = DEFAULT_MARGIN,
    ) -> None:
        self._platform = platform
        self._on_rating_cb = on_rating
        self._on_close_cb = on_close
        self._scale_max = scale_max
        self._width = width
        self._height = height
        self._margin = margin
        self._window = None
        self._ready = False

    def create(self):
        x, y = self._corner_position()
        self._window = webview.create_window(
            "PULSE check-in",
            url=str(_CHECKIN_HTML),
            js_api=_CheckinBridge(self),
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

    def _corner_position(self) -> tuple[int, int]:
        left, top, right, bottom = self._platform.get_work_area()
        return right - self._width - self._margin, bottom - self._height - self._margin

    def set_scale_max(self, scale_max: int) -> None:
        self._scale_max = scale_max

    def show_checkin(self) -> None:
        self._eval(f"window.pulse.startCheckin({int(self._scale_max)})")
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

    def _on_rating(self, value: int | None, skipped: bool) -> dict:
        return self._on_rating_cb(value, skipped)
