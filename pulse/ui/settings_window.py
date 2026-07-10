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

    def export_my_data(self, fmt: str = "csv", days=None) -> dict:
        """Export the reflection tables to a user-chosen folder. Local-only:
        the native folder dialog picks the destination, files are written
        there, nothing leaves the machine."""
        storage = self._win._storage
        window = self._win._window
        if storage is None or window is None:
            return {"ok": False, "message": "export unavailable"}
        chosen = window.create_file_dialog(webview.FOLDER_DIALOG)
        if not chosen:
            return {"ok": False, "cancelled": True}
        folder = chosen[0] if isinstance(chosen, (list, tuple)) else chosen
        from ..export import export_data
        try:
            files = export_data(
                storage, folder,
                fmt="json" if fmt == "json" else "csv",
                days=int(days) if days else None,
            )
        except Exception as e:
            return {"ok": False, "message": str(e)}
        return {"ok": True, "path": str(folder), "files": [f.name for f in files]}

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
        storage=None,
    ) -> None:
        self._settings = settings
        self._storage = storage
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
