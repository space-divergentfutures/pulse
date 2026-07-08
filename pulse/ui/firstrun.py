"""Guided first-run window (spec §6). Normal titled window (not a frameless corner
surface): the opening copy sets the contract, then a profile is chosen as a *tunable
starting point, not a diagnosis*."""

from __future__ import annotations

from collections.abc import Callable

import webview

from ..settings import profiles_payload
from . import WEB_DIR

_HTML = WEB_DIR / "firstrun.html"


class _FirstRunBridge:
    def __init__(self, win: "FirstRunWindow") -> None:
        self._win = win

    def get_profiles(self) -> list:
        return profiles_payload()

    def finish(self, profile_key: str | None) -> dict:
        self._win._on_finish(profile_key)
        return {"ok": True}

    def ready(self) -> dict:
        self._win._ready = True
        return {"ok": True}


class FirstRunWindow:
    def __init__(self, *, on_finish: Callable[[str | None], None]) -> None:
        self._on_finish_cb = on_finish
        self._window = None
        self._ready = False

    def create(self):
        self._window = webview.create_window(
            "Welcome to PULSE",
            url=str(_HTML),
            js_api=_FirstRunBridge(self),
            width=580,
            height=720,
            resizable=True,
            background_color="#101219",
        )
        return self._window

    def _on_finish(self, profile_key: str | None) -> None:
        self._on_finish_cb(profile_key)

    def destroy(self) -> None:
        if self._window is not None:
            self._window.destroy()
