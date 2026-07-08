"""System tray icon (spec §11) — pystray in a background thread.

Menu items: Pause/Resume · Break now · Today's count (display) · ─ ·
            Insights · Settings · ─ · Quit.

pystray owns its own thread; pywebview owns the main thread. All callbacks
here are safe to call from that background thread — pywebview's evaluate_js /
show / hide / destroy are internally queued onto the GUI event loop.
"""

from __future__ import annotations

import threading
from collections.abc import Callable


def _make_icon():
    """Build a 64×64 RGBA PIL image: teal ring + dark core + teal centre dot."""
    from PIL import Image, ImageDraw

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Outer teal ring
    draw.ellipse([2, 2, 62, 62], fill=(127, 209, 193, 255))
    # Dark inner circle
    draw.ellipse([14, 14, 50, 50], fill=(18, 20, 26, 255))
    # Centre teal dot (the "pulse")
    draw.ellipse([27, 27, 37, 37], fill=(127, 209, 193, 255))
    return img


class PulseTray:
    """System tray icon controller.

    ``start()`` launches pystray on a daemon thread. Call ``stop()`` before the
    process exits (or when the last pywebview window closes) so the icon disappears
    cleanly from the task bar.
    """

    def __init__(
        self,
        *,
        on_pause_resume: Callable[[], None],
        on_break_now: Callable[[], None],
        on_insights: Callable[[], None],
        on_settings: Callable[[], None],
        on_quit: Callable[[], None],
        get_today_count: Callable[[], int],
        get_paused: Callable[[], bool],
    ) -> None:
        self._on_pause_resume = on_pause_resume
        self._on_break_now = on_break_now
        self._on_insights = on_insights
        self._on_settings = on_settings
        self._on_quit = on_quit
        self._get_today_count = get_today_count
        self._get_paused = get_paused
        self._icon = None
        self._thread: threading.Thread | None = None

    # --- public ---------------------------------------------------------------

    def start(self) -> None:
        """Create the tray icon and start it on a daemon thread."""
        import pystray

        img = _make_icon()
        self._icon = pystray.Icon(
            "PULSE", img, "PULSE", self._build_menu()
        )
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass

    # --- menu -----------------------------------------------------------------

    def _build_menu(self):
        import pystray

        def _pause_text(item):
            return "Resume" if self._get_paused() else "Pause"

        def _today_text(item):
            n = self._get_today_count()
            return f"Today: {n} break{'s' if n != 1 else ''}"

        return pystray.Menu(
            pystray.MenuItem(_pause_text, self._cb_pause_resume),
            pystray.MenuItem("Break now", self._cb_break_now),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(_today_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Insights", self._cb_insights),
            pystray.MenuItem("Settings", self._cb_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._cb_quit),
        )

    # pystray callbacks receive (icon, item) — wrap to the simpler zero-arg API.
    def _cb_pause_resume(self, icon, item) -> None:  # noqa: ARG002
        self._on_pause_resume()

    def _cb_break_now(self, icon, item) -> None:
        self._on_break_now()

    def _cb_insights(self, icon, item) -> None:
        self._on_insights()

    def _cb_settings(self, icon, item) -> None:
        self._on_settings()

    def _cb_quit(self, icon, item) -> None:
        self._on_quit()
