"""The corner countdown widget controller (spec §5a) — the signature interaction.

A frameless, always-on-top, opaque rounded card that hugs the bottom-right corner near
the system clock (the Step 0 spike proved this works in pywebview; transparency does
not, so the card is opaque). Python owns the truth and pushes state into the page; the
page renders it and smooths the visible tick.

The controller is deliberately decoupled from the engine: it takes callbacks, so the
app loop (Step 3) decides what "Break now" and "Done" mean. This keeps the signature
interaction — advance warning, you choose the moment, self-started timer — in one place.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import webview

from ..platform.base import PlatformInterface
from . import WEB_DIR

_WIDGET_HTML = WEB_DIR / "widget.html"

# Small, but "sized to actually be readable" (§5a) — near the clock, not a tooltip.
# NOTE: on Windows, pywebview's frameless window reserves ~16px width and ~39px height
# of invisible chrome around the WebView2 client area, so these OUTER sizes yield a
# ~232x117 client area — enough for the ~104px card content with breathing room.
DEFAULT_WIDTH = 248
DEFAULT_HEIGHT = 156
DEFAULT_MARGIN = 12


class _WidgetBridge:
    """js_api object. pywebview calls these from its GUI thread when the user acts."""

    def __init__(self, widget: "CornerWidget") -> None:
        self._widget = widget

    def break_now(self) -> dict:
        self._widget._fire("break_now")
        return {"ok": True}

    def done(self) -> dict:
        self._widget._fire("done")
        return {"ok": True}

    def timer_finished(self) -> dict:
        self._widget._fire("timer_finished")
        return {"ok": True}

    def wave_off(self) -> dict:
        self._widget._fire("wave_off")
        return {"ok": True}

    def ready(self) -> dict:
        self._widget._ready = True
        return {"ok": True}


class CornerWidget:
    def __init__(
        self,
        platform: PlatformInterface,
        *,
        on_break_now: Callable[[], None] | None = None,
        on_done: Callable[[], None] | None = None,
        on_timer_finished: Callable[[], None] | None = None,
        on_wave_off: Callable[[], None] | None = None,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        margin: int = DEFAULT_MARGIN,
        start_hidden: bool = False,
    ) -> None:
        self._platform = platform
        self._width = width
        self._height = height
        self._margin = margin
        self._start_hidden = start_hidden
        self._callbacks = {
            "break_now": on_break_now,
            "done": on_done,
            "timer_finished": on_timer_finished,
            "wave_off": on_wave_off,
        }
        self._window = None
        self._ready = False

    # --- lifecycle -------------------------------------------------------------

    def create(self):
        """Create the pywebview window. Call before webview.start(); positioning uses
        the taskbar-excluded work area so the card sits by the clock."""
        x, y = self._corner_position()
        self._window = webview.create_window(
            "PULSE",
            url=str(_WIDGET_HTML),
            js_api=_WidgetBridge(self),
            width=self._width,
            height=self._height,
            x=x,
            y=y,
            frameless=True,        # proven in Step 0
            on_top=True,           # proven in Step 0
            resizable=False,
            transparent=False,     # opaque baseline (Step 0: transparency unreliable)
            background_color="#12141a",
            easy_drag=False,
            hidden=self._start_hidden,
        )
        return self._window

    def _corner_position(self) -> tuple[int, int]:
        left, top, right, bottom = self._platform.get_work_area()
        x = right - self._width - self._margin
        y = bottom - self._height - self._margin
        return x, y

    # --- state the app pushes in -----------------------------------------------

    def show_countdown(self, remaining_seconds: float, escalated: bool = False) -> None:
        """Advance warning (§5a). Re-push each poll with the authoritative ACTIVE-time
        remaining; the page smooths the tick between calls. escalated=True once the
        mark has passed (gentle amber pulse; never a screen takeover)."""
        self._eval(
            f"window.pulse.showCountdown({float(remaining_seconds)}, "
            f"{json.dumps(bool(escalated))})"
        )

    def start_timer(self, seconds: float) -> None:
        """Begin the self-started movement timer — the user started it, it is not on
        the app's clock (§5a point 3)."""
        self._eval(f"window.pulse.startTimer({float(seconds)})")

    def show_done(self) -> None:
        self._eval("window.pulse.showDone()")

    def show_training_ready(self) -> None:
        """Show the 'training break ready — whenever you're ready' state (§5b)."""
        self._eval("window.pulse.showTraining()")

    def show_focus_mode(self, enabled: bool) -> None:
        """Push focus-mode state to JS: suppresses amber pulse, shows wave-off button."""
        self._eval(f"window.pulse.setFocusMode({json.dumps(bool(enabled))})")

    def show(self) -> None:
        if self._window is not None:
            self._window.show()

    def hide(self) -> None:
        if self._window is not None:
            self._window.hide()

    def destroy(self) -> None:
        if self._window is not None:
            self._window.destroy()

    # --- internals -------------------------------------------------------------

    def _eval(self, js: str) -> None:
        if self._window is not None:
            self._window.evaluate_js(js)

    def _fire(self, name: str) -> None:
        cb = self._callbacks.get(name)
        if cb is not None:
            cb()
