"""Insights window (spec §7/§10) — weekly summary, unlock meter, pattern reveal.

A standalone windowed view (not frameless); opened from the tray menu (Step 11).
Shows the day/week dot chart, the progress meter toward the evidence floor, and
pattern cards that reveal only once the floor is honestly met.
"""

from __future__ import annotations

from collections.abc import Callable

import webview

from . import WEB_DIR

_INSIGHTS_HTML = WEB_DIR / "insights.html"

WIDTH = 480
HEIGHT = 540


class _InsightsBridge:
    def __init__(self, win: "InsightsWindow") -> None:
        self._win = win

    def load(self) -> dict:
        return self._win._load_cb()

    def close(self) -> dict:
        self._win.hide()
        return {"ok": True}

    def ready(self) -> dict:
        self._win._ready = True
        return {"ok": True}


class InsightsWindow:
    def __init__(self, load_cb: Callable[[], dict]) -> None:
        self._load_cb = load_cb
        self._window = None
        self._ready = False

    def create(self):
        self._window = webview.create_window(
            "PULSE — Insights",
            url=str(_INSIGHTS_HTML),
            js_api=_InsightsBridge(self),
            width=WIDTH,
            height=HEIGHT,
            resizable=True,
            on_top=False,
            hidden=True,
        )
        return self._window

    def show(self) -> None:
        if self._window is not None:
            self._window.show()
            # Reload data each time the window opens — data accumulates between sessions.
            self._window.evaluate_js(
                "window.pulse && window.pulse.refresh && window.pulse.refresh()"
            )

    def hide(self) -> None:
        if self._window is not None:
            self._window.hide()

    def destroy(self) -> None:
        if self._window is not None:
            self._window.destroy()
