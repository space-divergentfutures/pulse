"""PULSE orchestrator (spec §3) — wires presence → engine → UI on the light layer.

pywebview owns the main thread; the presence poll loop runs on a background thread and
drives the corner widget and break card. This is the Milestone-1 light-layer loop:

    work → (corner countdown warns) → you hit "Break now" → break card with a movement
    suggestion + hydration + a self-started timer → Done → back to work.

Gentle by default: no hard-lock, no snooze on the light layer (§5a). The engine stores
only aggregates; nothing here records what you were doing.
"""

from __future__ import annotations

import threading
import time

import webview

from .config import TimingConfig
from .content import hydration_prompt_at, light_movement_at
from .platform import get_platform
from .platform.base import PlatformInterface
from .reflection import graph_payload
from .state_machine import EngineEvent, SessionEngine, SessionState
from .storage import PulseStorage
from .ui.break_card import BreakCard
from .ui.checkin import CheckinCard
from .ui.widget import CornerWidget


class PulseApp:
    def __init__(
        self,
        config: TimingConfig | None = None,
        *,
        platform: PlatformInterface | None = None,
        storage: PulseStorage | None = None,
        db_path: str | None = None,
        scale_max: int = 10,
        poll_interval_seconds: float = 5.0,
    ) -> None:
        self.config = config or TimingConfig()
        self.platform = platform or get_platform()
        self.storage = storage or PulseStorage(db_path)
        self.scale_max = scale_max
        self.poll_interval = poll_interval_seconds

        self.engine = SessionEngine(self.config)
        self._lock = threading.Lock()  # engine is touched by poll thread + GUI callbacks
        self._stop = threading.Event()

        self._due = False              # the mark has passed; widget escalates
        self._widget_visible = False
        self._in_break = False
        self._move_cursor = 0
        self._hydration_cursor = 0
        self._persisted_active_s = 0.0  # active seconds already written to storage

        self.widget = CornerWidget(
            self.platform,
            on_break_now=self._on_break_now,
            start_hidden=True,
        )
        self.break_card = BreakCard(
            self.platform,
            on_done=self._on_break_done,
        )
        self.checkin = CheckinCard(
            self.platform,
            on_rating=self._on_rating,
            on_close=self._on_checkin_close,
            scale_max=self.scale_max,
        )

    # --- lifecycle -------------------------------------------------------------

    def run(self, _on_started=None) -> None:
        """Create the windows and start the GUI loop (blocks). The poll loop runs on a
        daemon thread once pywebview is up. ``_on_started`` is an optional hook used by
        verification harnesses to drive the UI; it runs after the loop starts."""
        self.platform.prepare_high_dpi()
        self.widget.create()
        self.break_card.create()
        self.checkin.create()

        def _startup() -> None:
            threading.Thread(target=self._poll_loop, daemon=True).start()
            if _on_started is not None:
                _on_started()

        webview.start(_startup, debug=False)

    def stop(self) -> None:
        self._stop.set()

    # --- the poll loop (background thread) -------------------------------------

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            now = self.platform.get_monotonic_ms()
            idle = self.platform.get_idle_seconds()
            locked = self.platform.is_session_locked()

            with self._lock:
                events = self.engine.tick(now, idle, locked)
                state = self.engine.session_state
                short_s = self.engine.snapshot().short_break_seconds

            for event in events:
                self._handle_event(event)

            # Keep the corner countdown current while it's showing (ACTIVE-time based,
            # so it pauses when the person goes idle — re-pushed here every poll).
            if not self._in_break and state is SessionState.WARN:
                remaining = max(0.0, self.config.light_interval_minutes * 60.0 - short_s)
                self.widget.show_countdown(remaining, escalated=self._due or remaining <= 0)

            self._stop.wait(self.poll_interval)

    def _handle_event(self, event: EngineEvent) -> None:
        if event is EngineEvent.WARNING_START:
            self._due = False
            if not self._widget_visible and not self._in_break:
                self.widget.show()
                self._widget_visible = True
        elif event is EngineEvent.BREAK_DUE:
            self._due = True
        elif event is EngineEvent.AWAY_RESET:
            # The person took a real break on their own — stand down quietly.
            self._due = False
            if self._widget_visible:
                self.widget.hide()
                self._widget_visible = False
        # BOUNDARY_DUE and USEFUL_CHECK_DUE are handled in later build steps.

    # --- UI callbacks (GUI thread) --------------------------------------------

    def _on_break_now(self) -> None:
        """User hit "Break now" on the corner widget. Start a self-timed light break
        with a movement suggestion + hydration line."""
        with self._lock:
            self.engine.start_break()
        self._due = False
        if self._widget_visible:
            self.widget.hide()
            self._widget_visible = False
        self._in_break = True

        movement = light_movement_at(self._move_cursor)
        hydration = hydration_prompt_at(self._hydration_cursor)
        self._move_cursor += 1
        self._hydration_cursor += 1

        self.break_card.start_break(
            name=movement.name,
            detail=movement.detail,
            hydration=hydration,
            seconds=self.config.light_break_seconds,
        )

    def _on_break_done(self) -> None:
        """Break finished (honor-based). The check-in rides on the break you're already
        taking — one interruption, not two (§7)."""
        with self._lock:
            self.engine.complete_break()
        self._persist_active_time()
        self.break_card.hide()
        self.checkin.show_checkin()
        # _in_break stays True across the check-in so the widget won't re-warn under it.

    def _on_rating(self, value: int | None, skipped: bool) -> dict:
        """Store the one-tap rating (or skip) and return the fresh graph payload so the
        page can show the graph immediately — the instant feedback is the reward (§7)."""
        with self._lock:
            self.storage.add_checkin(value, skipped=skipped)
            payload = graph_payload(self.storage, self.config, self.scale_max)
        return payload

    def _on_checkin_close(self) -> None:
        self.checkin.hide()
        self._in_break = False

    def _persist_active_time(self) -> None:
        """Write the active minutes accrued since the last persist into today's row
        (per-machine, additive — §8). Best-effort; safe to call often."""
        with self._lock:
            lifetime_s = self.engine.snapshot().lifetime_active_seconds
        delta_s = lifetime_s - self._persisted_active_s
        if delta_s > 0:
            self.storage.add_active_minutes(delta_s / 60.0)
            self._persisted_active_s = lifetime_s


def main() -> None:
    PulseApp().run()


if __name__ == "__main__":
    main()
