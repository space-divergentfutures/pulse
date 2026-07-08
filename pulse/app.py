"""PULSE orchestrator (spec §3) — wires presence → engine → UI on the light layer.

pywebview owns the main thread; the presence poll loop runs on a background thread and
drives the corner widget and break card. This is the Milestone-1 light-layer loop:

    work → (corner countdown warns) → you hit "Break now" → break card with a movement
    suggestion + hydration + a self-started timer → Done → back to work.

Gentle by default: no hard-lock, no snooze on the light layer (§5a). The engine stores
only aggregates; nothing here records what you were doing.
"""

from __future__ import annotations

import os
import threading
import time

import webview

from .config import TimingConfig
from .content import hydration_prompt_at, light_movement_at
from .meal import active_window_now
from .platform import get_platform
from .platform.base import PlatformInterface
from .reflection import compute_patterns, graph_payload, weekly_payload
from .settings import Settings
from .state_machine import EngineEvent, SessionEngine, SessionState
from .storage import PulseStorage
from .theme import build_vars, inject_theme
from .training import big_break_payload, pick_big_break_options, pick_session, session_payload
from .ui.break_card import BreakCard
from .ui.checkin import CheckinCard
from .ui.firstrun import FirstRunWindow
from .ui.insights import InsightsWindow
from .ui.settings_window import SettingsWindow
from .ui.training_card import TrainingCard
from .ui.widget import CornerWidget


def _startup_command() -> str:
    """Return the launch command for the HKCU Run key, or '' in development."""
    import sys
    if getattr(sys, "frozen", False):
        return sys.executable  # PyInstaller bundle: exe is the command
    return ""  # development — don't register; packaging handles it in Step 13


def _sync_startup_key(platform, settings) -> None:
    """Sync the HKCU Run key with the start_with_windows setting (§11)."""
    enabled = settings.get("start_with_windows")
    cmd = _startup_command()
    try:
        if enabled and cmd:
            platform.set_startup_enabled(True, cmd)
        elif not enabled:
            platform.set_startup_enabled(False)
        # If enabled but no cmd (development), skip silently.
    except Exception:
        pass  # registry may be unavailable in sandboxed test environments


class PulseApp:
    def __init__(
        self,
        config: TimingConfig | None = None,
        *,
        platform: PlatformInterface | None = None,
        storage: PulseStorage | None = None,
        db_path: str | None = None,
        scale_max: int | None = None,
        poll_interval_seconds: float = 5.0,
    ) -> None:
        self.platform = platform or get_platform()
        self.storage = storage or PulseStorage(db_path)
        self.settings = Settings(self.storage)
        # Every user-facing setting lives in SQLite (§6/§8); the engine config is derived
        # from it. An explicit config/scale_max still wins (used by verification harnesses).
        self.config = config if config is not None else self.settings.to_timing_config()
        self.scale_max = scale_max if scale_max is not None else self.settings.scale_max()
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
        self._current_meal_window: str | None = None

        self._training_pending = False   # BOUNDARY_DUE fired; widget in training mode
        self._training_deferred = False  # BOUNDARY_DUE fired while focus mode — queued
        self._in_training = False
        self._training_session_cursor = 0  # rotates through exercise category pairs
        self._theme_applied = False      # inject CSS vars on first poll after windows load

        # Step 9: useful-check state and the checkin-id carried across rate → context.
        self._useful_check_pending = False
        self._useful_check_seeded = False   # seed engine counter from storage on first tick
        self._last_checkin_id: str | None = None

        # Step 11: pause flag + tray handle.
        self._paused = False
        self._tray = None

        # Step 12: optional PocketBase sync handle.
        self._sync = None

        self.widget = CornerWidget(
            self.platform,
            on_break_now=self._on_break_now,
            on_wave_off=self._on_wave_off,
            start_hidden=True,
        )
        self.break_card = BreakCard(
            self.platform,
            on_done=self._on_break_done,
            on_meal_settled=self._on_meal_settled,
        )
        self.checkin = CheckinCard(
            self.platform,
            on_rating=self._on_rating,
            on_context=self._on_context,
            on_useful_check=self._on_useful_check_response,
            on_close=self._on_checkin_close,
            scale_max=self.scale_max,
        )
        self.insights_window = InsightsWindow(load_cb=self._load_insights)
        self.settings_window = SettingsWindow(
            self.settings, on_changed=self._reload_config_from_settings
        )
        self.training_card = TrainingCard(
            self.platform,
            on_exercise_outcome=self._on_exercise_outcome,
            on_session_complete=self._on_training_complete,
            on_close=self._on_training_close,
            on_big_break_done=self._on_big_break_done,
        )
        self._firstrun: FirstRunWindow | None = None

    # --- lifecycle -------------------------------------------------------------

    def run(self, _on_started=None) -> None:
        """Create the windows and start the GUI loop (blocks). The poll loop runs on a
        daemon thread once pywebview is up. ``_on_started`` is an optional hook used by
        verification harnesses to drive the UI; it runs after the loop starts."""
        self.platform.prepare_high_dpi()
        self.widget.create()
        self.break_card.create()
        self.checkin.create()
        self.insights_window.create()
        self.settings_window.create()
        self.training_card.create()

        # First launch walks through the core choices once, with the explainers (§6).
        if not self.settings.first_run_complete:
            self._firstrun = FirstRunWindow(on_finish=self._on_first_run_finish)
            self._firstrun.create()

        def _startup() -> None:
            self._start_tray()
            threading.Thread(target=self._poll_loop, daemon=True).start()
            if _on_started is not None:
                _on_started()

        webview.start(_startup, debug=False)
        # webview.start() returns when all windows are destroyed (e.g. Quit).
        if self._tray is not None:
            self._tray.stop()
        self.storage.close()

    # --- settings / first-run --------------------------------------------------

    def _on_first_run_finish(self, profile_key: str | None) -> None:
        """First-run finished: apply the chosen profile (or keep gentle defaults), mark
        it done, and rebuild the engine config from the new settings."""
        if profile_key:
            self.settings.apply_profile(profile_key)
        self.settings.mark_first_run_complete()
        self._reload_config_from_settings()
        if self._firstrun is not None:
            self._firstrun.destroy()
            self._firstrun = None

    def open_settings(self) -> None:
        self.settings_window.show()

    def open_insights(self) -> None:
        self.insights_window.show()

    def _load_insights(self) -> dict:
        with self._lock:
            return weekly_payload(self.storage, self.config, self.scale_max)

    def _start_tray(self) -> None:
        from .ui.tray import PulseTray
        self._tray = PulseTray(
            on_pause_resume=self._on_pause_resume,
            on_break_now=self._on_break_now,
            on_insights=self.open_insights,
            on_settings=self.open_settings,
            on_quit=self._on_quit,
            get_today_count=lambda: self.storage.training_count_today(),
            get_paused=lambda: self._paused,
        )
        self._tray.start()
        # Sync HKCU startup key with the setting (e.g. after a reinstall to a new path).
        _sync_startup_key(self.platform, self.settings)
        self._start_sync()

    def _start_sync(self) -> None:
        """Start PocketBase sync if all three requirements are met: setting enabled,
        sync_url in config.yaml, and PULSE_PB_TOKEN in the environment."""
        if not self.settings.get("sync_enabled"):
            return
        from .machine_config import MachineConfig
        mc = MachineConfig.load()
        if not mc.sync_url:
            return
        token = os.environ.get("PULSE_PB_TOKEN", "")
        if not token:
            return
        from .sync import PocketBaseSync, SyncClient
        client = SyncClient(mc.sync_url, token)
        self._sync = PocketBaseSync(self.storage, client)
        self._sync.start()

    def _restart_sync_if_needed(self) -> None:
        """Called after settings change: start or stop sync to match the new setting."""
        enabled = self.settings.get("sync_enabled")
        if self._sync is not None and not enabled:
            self._sync.stop()
            self._sync = None
        elif self._sync is None and enabled:
            self._start_sync()

    def _on_pause_resume(self) -> None:
        self._paused = not self._paused
        if self._paused and self._widget_visible:
            self.widget.hide()
            self._widget_visible = False

    def _on_quit(self) -> None:
        """Tray Quit: stop the poll loop, destroy all windows, clean up."""
        self._stop.set()
        if self._sync is not None:
            self._sync.stop()
            self._sync = None
        controllers = [
            self.widget, self.break_card, self.checkin,
            self.insights_window, self.settings_window, self.training_card,
        ]
        if self._firstrun is not None:
            controllers.append(self._firstrun)
        for ctrl in controllers:
            try:
                ctrl.destroy()
            except Exception:
                pass

    def _reload_config_from_settings(self) -> None:
        """Apply a settings change to the live engine immediately (§6: fully tunable)."""
        with self._lock:
            self.config = self.settings.to_timing_config()
            self.engine.config = self.config
        self.scale_max = self.settings.scale_max()
        self.checkin.set_scale_max(self.scale_max)
        self._apply_theme_to_all()
        _sync_startup_key(self.platform, self.settings)
        self._restart_sync_if_needed()

    def _apply_theme_to_all(self) -> None:
        """Inject current appearance CSS vars into every live pywebview window."""
        vars = build_vars(self.settings)
        controllers = [
            self.widget, self.break_card, self.checkin,
            self.insights_window, self.settings_window, self.training_card,
        ]
        if self._firstrun is not None:
            controllers.append(self._firstrun)
        for ctrl in controllers:
            win = getattr(ctrl, "_window", None)
            if win is not None:
                inject_theme(win, vars)

    def stop(self) -> None:
        self._stop.set()

    # --- the poll loop (background thread) -------------------------------------

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            if not self._theme_applied:
                self._apply_theme_to_all()
                self._theme_applied = True

            # Seed the useful-check accumulator from storage so the 5.5-hour cadence
            # survives restarts and carries the correct remainder across days (§7).
            if not self._useful_check_seeded:
                saved_ms = self.storage.get_useful_check_ms()
                if saved_ms > 0:
                    with self._lock:
                        self.engine._useful_check_ms = saved_ms
                self._useful_check_seeded = True

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
            if not self._in_break and not self._paused and state is SessionState.WARN:
                focus_mode = self.settings.get("focus_mode_enabled")
                remaining = max(0.0, self.config.light_interval_minutes * 60.0 - short_s)
                # In focus mode the widget never escalates — stays quiet, purely advisory.
                escalated = (self._due or remaining <= 0) and not focus_mode
                self.widget.show_countdown(remaining, escalated=escalated)
                self.widget.show_focus_mode(focus_mode)

            self._stop.wait(self.poll_interval)

    def _handle_event(self, event: EngineEvent) -> None:
        # AWAY_RESET is always processed — a natural break clears pending state even
        # while paused, so unpause doesn't immediately re-warn the user.
        if event is EngineEvent.AWAY_RESET:
            self._due = False
            self._training_pending = False
            self._training_deferred = False
            if self._widget_visible:
                self.widget.hide()
                self._widget_visible = False
            return

        if self._paused:
            return  # suppress all other events while user has manually paused

        if event is EngineEvent.WARNING_START:
            self._due = False
            if not self._widget_visible and not self._in_break:
                self.widget.show()
                self._widget_visible = True
        elif event is EngineEvent.BREAK_DUE:
            self._due = True
        elif event is EngineEvent.BOUNDARY_DUE:
            if self._can_offer_training() and not self._in_break and not self._in_training:
                if self.settings.get("focus_mode_enabled"):
                    # Focus Guard: defer training to the next natural break — don't interrupt.
                    self._training_deferred = True
                else:
                    self._training_pending = True
                    if not self._widget_visible:
                        self.widget.show()
                        self._widget_visible = True
                    self.widget.show_training_ready()
        elif event is EngineEvent.USEFUL_CHECK_DUE:
            # Persist the remainder so it carries across restarts (§7: "persistent across days").
            with self._lock:
                remainder = self.engine._useful_check_ms
            self.storage.save_useful_check_ms(remainder)
            # Only offer the check from Stage 2 onward — no point asking before block types exist.
            if self.storage.reflection_stage() >= 2:
                self._useful_check_pending = True

    # --- UI callbacks (GUI thread) --------------------------------------------

    def _can_offer_training(self) -> bool:
        if not self.settings.get("training_enabled"):
            return False
        cap = int(self.config.max_training_sessions_per_day)
        return self.storage.training_count_today() < cap

    def _on_break_now(self) -> None:
        """'Break now' / 'Do it' on the corner widget — routes to training or light break."""
        if self._training_pending or self._training_deferred:
            self._training_deferred = False  # consume the deferred flag before routing
            self._on_training_now()
            return
        # Light break path — movement suggestion + hydration + optional meal question.
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

        meal_prompt = False
        self._current_meal_window = None
        if self.settings.get("meal_windows_enabled"):
            win = active_window_now()
            if win and not self.storage.meal_settled_today(win):
                meal_prompt = True
                self._current_meal_window = win

        self.break_card.start_break(
            name=movement.name,
            detail=movement.detail,
            hydration=hydration,
            seconds=self.config.light_break_seconds,
            meal_prompt=meal_prompt,
            meal_window=self._current_meal_window or "",
        )

    def _on_meal_settled(
        self, window_name: str, answered: str, extended_minutes: float | None
    ) -> None:
        """Meal-window answer received from the break card. Store it; the break
        continues normally from here — Python doesn't need to intervene further."""
        self.storage.record_meal_prompt(window_name, answered, extended_minutes)

    def _on_wave_off(self) -> None:
        """User dismissed the widget in Focus Guard mode — hide without starting a break.
        The widget won't reappear until the next WARN cycle; _due and engine state are
        untouched so the clock continues as normal."""
        if self._widget_visible:
            self.widget.hide()
            self._widget_visible = False

    # --- training flow --------------------------------------------------------

    def _on_training_now(self) -> None:
        """User accepted a training break. Hide widget, pick a session, show card."""
        self._training_pending = False
        self._in_training = True
        if self._widget_visible:
            self.widget.hide()
            self._widget_visible = False

        enforcement = self.settings.get("enforcement_training")
        hard_lock = enforcement == "hard_lock"

        session = pick_session(self.storage, self._training_session_cursor)
        bb_opts = pick_big_break_options(3)

        # Both regular session payload and big_break options travel together so the
        # get-ready screen's "go outside" button can switch without another round-trip.
        payload = session_payload(session, hard_lock=hard_lock)
        payload["options"] = big_break_payload(bb_opts)["options"]
        self.training_card.start_session(payload)

    def _on_exercise_outcome(self, exercise_id: str, outcome: str) -> dict:
        """Record each exercise's outcome and return progression data to the JS."""
        if outcome == "done":
            result = self.storage.record_exercise_done(exercise_id)
        elif outcome == "skip":
            result = self.storage.record_exercise_skip(exercise_id)
        elif outcome == "pain":
            self.storage.record_exercise_pain(exercise_id)
            result = self.storage.record_exercise_skip(exercise_id)
        else:
            result = {"level_changed": False, "new_level": 1}
        return result

    def _on_training_complete(self, outcomes: list) -> None:
        """All exercises done. Record the break, persist active time, queue check-in."""
        enforcement = self.settings.get("enforcement_training")
        self.storage.record_break("training", enforcement, "completed")
        with self._lock:
            self.engine.record_training_session()
        self._training_session_cursor += 1
        self._persist_active_time()

    def _on_training_close(self) -> None:
        """Training card closed after completion — show check-in."""
        self.training_card.hide()
        self._in_training = False
        self._show_checkin()

    def _on_big_break_done(self) -> None:
        """12-min Big Break finished. Record, persist, queue check-in."""
        enforcement = self.settings.get("enforcement_training")
        self.storage.record_break("big", enforcement, "completed")
        with self._lock:
            self.engine.record_training_session()
        self._training_session_cursor += 1
        self._persist_active_time()
        self.training_card.hide()
        self._in_training = False
        self._show_checkin()

    def _on_break_done(self) -> None:
        """Break finished (honor-based). The check-in rides on the break you're already
        taking — one interruption, not two (§7)."""
        with self._lock:
            self.engine.complete_break()
        self._persist_active_time()
        self.break_card.hide()
        self._show_checkin()
        # _in_break stays True across the check-in so the widget won't re-warn under it.

    def _show_checkin(self) -> None:
        stage = self.storage.reflection_stage()
        self.checkin.show_checkin(stage)

    def _on_rating(self, value: int | None, skipped: bool) -> dict:
        """Store the one-tap rating (or skip) and return the graph payload.
        Stage and useful_check_pending are included so JS can decide the next view (§7)."""
        with self._lock:
            cid = self.storage.add_checkin(value, skipped=skipped)
            payload = graph_payload(self.storage, self.config, self.scale_max)
        self._last_checkin_id = cid
        stage = self.storage.reflection_stage()
        payload["stage"] = stage
        payload["skipped"] = skipped
        # useful_check only applies in Stage 2+ and not on a skip (skip is already an opt-out).
        payload["useful_check_pending"] = self._useful_check_pending and stage >= 2 and not skipped
        return payload

    def _on_context(self, block_type: str | None, note: str | None) -> dict:
        """Stage 2/3: attach block_type and note to the already-stored checkin,
        then return the updated graph payload so the graph view can render."""
        cid = self._last_checkin_id
        with self._lock:
            if cid:
                self.storage.update_checkin_context(cid, block_type, note)
            payload = graph_payload(self.storage, self.config, self.scale_max)
        stage = self.storage.reflection_stage()
        payload["stage"] = stage
        payload["useful_check_pending"] = self._useful_check_pending and stage >= 2
        return payload

    def _on_useful_check_response(self, response: str) -> dict:
        """User answered the "was this useful?" question. Clear the pending flag.
        'stop' means disable further block_type prompts — handled in Step 10."""
        self._useful_check_pending = False
        return {"ok": True}

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
