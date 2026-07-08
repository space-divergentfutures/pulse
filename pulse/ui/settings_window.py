"""Settings window (spec §6). Renders itself from the settings catalogue, saves each
change live, and carries the "?" explainer on every setting. Normal titled window."""

from __future__ import annotations

from collections.abc import Callable

import webview

from ..settings import Settings, catalogue_payload
from . import WEB_DIR

_HTML = WEB_DIR / "settings.html"


class _SettingsBridge:
    def __init__(self, win: "SettingsWindow") -> None:
        self._win = win

    def get_catalogue(self) -> dict:
        return catalogue_payload(self._win._settings)

    def set_setting(self, key: str, value) -> dict:
        self._win._settings.set(key, value)
        self._win._notify_changed()
        return {"ok": True}

    def apply_profile(self, profile_key: str) -> dict:
        self._win._settings.apply_profile(profile_key)
        self._win._notify_changed()
        return catalogue_payload(self._win._settings)

    def close(self) -> dict:
        self._win.hide()
        return {"ok": True}

    def ready(self) -> dict:
        self._win._ready = True
        return {"ok": True}


class SettingsWindow:
    def __init__(
        self,
        settings: Settings,
        *,
        on_changed: Callable[[], None] | None = None,
    ) -> None:
        self._settings = settings
        self._on_changed = on_changed
        self._window = None
        self._ready = False

    def create(self):
        self._window = webview.create_window(
            "PULSE settings",
            url=str(_HTML),
            js_api=_SettingsBridge(self),
            width=640,
            height=760,
            resizable=True,
            background_color="#101219",
            hidden=True,
        )
        return self._window

    def show(self) -> None:
        if self._window is not None:
            self._window.show()

    def hide(self) -> None:
        if self._window is not None:
            self._window.hide()

    def destroy(self) -> None:
        if self._window is not None:
            self._window.destroy()

    def _notify_changed(self) -> None:
        if self._on_changed is not None:
            self._on_changed()
