/* PULSE corner widget behaviour (spec §5a).
 *
 * Python (the controller) owns the truth and pushes state in; JS renders it and
 * smooths the display between pushes so the number ticks every second instead of
 * every 5s poll. Two clocks, deliberately:
 *   - countdown/due : ACTIVE-time based. Python re-pushes the authoritative value each
 *                     poll (it pauses when you go idle); JS only interpolates between.
 *   - timer         : the self-started break. Wall-clock, JS-owned — you started it,
 *                     it is not on the app's clock.
 */
(function () {
  "use strict";

  const card = document.getElementById("card");
  const labelEl = document.getElementById("label");
  const countEl = document.getElementById("count");
  const subEl = document.getElementById("sub");
  const btn = document.getElementById("actionBtn");
  const waveOffBtn = document.getElementById("waveOffBtn");

  const state = {
    phase: "countdown",      // countdown | due | timer | done | training | reading
    remaining: 0,            // seconds (derived from countdownEndAt when set)
    countdownEndAt: null,    // ms epoch deadline for the countdown (wall-clock)
    timerEndAt: null,        // ms epoch, for the self-started timer
    timerFired: false,
    readingMinutes: 30,      // shown on the reading-ready card
  };

  function api() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
  }

  function fmt(sec) {
    sec = Math.max(0, Math.round(sec));
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return m + ":" + String(s).padStart(2, "0");
  }

  function paint() {
    card.setAttribute("data-phase", state.phase);
    if (state.phase === "countdown") {
      labelEl.textContent = "Break in";
      subEl.textContent = "finish your thought";
      btn.textContent = "Break now";
      countEl.textContent = fmt(state.remaining);
    } else if (state.phase === "due") {
      labelEl.textContent = "Time to move";
      subEl.textContent = "whenever you're ready";
      btn.textContent = "Break now";
      countEl.textContent = fmt(state.remaining);
    } else if (state.phase === "timer") {
      labelEl.textContent = "Moving";
      subEl.textContent = "get up, move, come back";
      btn.textContent = "Done";
      countEl.textContent = fmt(state.remaining);
    } else if (state.phase === "done") {
      labelEl.textContent = "Nice";
      subEl.textContent = "back to it when you're ready";
      btn.textContent = "Done";
      countEl.textContent = "✓";
    } else if (state.phase === "training") {
      labelEl.textContent = "Training break";
      subEl.textContent = "finish your thought";
      btn.textContent = "Do it";
      countEl.textContent = "90 min";
    } else if (state.phase === "reading") {
      labelEl.textContent = "Reading break";
      subEl.textContent = "whenever you're ready — grab your book";
      btn.textContent = "Do it";
      countEl.textContent = state.readingMinutes + " min";
    }
  }

  // One heartbeat drives the visible tick for both clocks.
  setInterval(function () {
    if (state.phase === "countdown" || state.phase === "due") {
      if (state.countdownEndAt !== null) {
        state.remaining = Math.max(0, (state.countdownEndAt - Date.now()) / 1000);
      } else if (state.remaining > 0) {
        state.remaining -= 1;
      }
      paint();
    } else if (state.phase === "timer") {
      const left = (state.timerEndAt - Date.now()) / 1000;
      state.remaining = left;
      if (left <= 0 && !state.timerFired) {
        state.timerFired = true;
        const a = api();
        if (a) a.timer_finished();
        state.phase = "done";
      }
      paint();
    }
  }, 1000);

  btn.addEventListener("click", function () {
    const a = api();
    if (!a) return;
    if (state.phase === "timer" || state.phase === "done") {
      a.done();
    } else {
      // countdown | due | training | reading — Python's break_now routes to the
      // pending training/reading session or a plain light break as appropriate.
      a.break_now();
    }
  });

  waveOffBtn.addEventListener("click", function () {
    const a = api();
    if (a) a.wave_off();
  });

  // --- the interface Python drives via evaluate_js ---
  window.pulse = {
    // ACTIVE-time countdown; escalated => the mark has passed (phase "due").
    showCountdown: function (remainingSeconds, escalated) {
      state.phase = escalated ? "due" : "countdown";
      const now = Date.now();
      const newEndAt = now + remainingSeconds * 1000;
      const exhausted = state.countdownEndAt !== null && state.countdownEndAt < now;
      if (state.countdownEndAt === null || exhausted || newEndAt <= state.countdownEndAt) {
        state.countdownEndAt = newEndAt;
      }
      state.remaining = Math.max(0, (state.countdownEndAt - now) / 1000);
      paint();
    },
    // Start the self-started movement timer (wall-clock, JS-owned).
    startTimer: function (seconds) {
      state.phase = "timer";
      state.timerFired = false;
      state.timerEndAt = Date.now() + seconds * 1000;
      state.remaining = seconds;
      paint();
    },
    showDone: function () {
      state.phase = "done";
      paint();
    },
    showTraining: function () {
      state.phase = "training";
      paint();
    },
    // Reading session ready (day plan) — same gentle offer pattern as training.
    showReading: function (minutes) {
      state.phase = "reading";
      state.readingMinutes = Math.round(minutes) || 30;
      paint();
    },
    // Push focus mode state — suppresses amber escalation, shows wave-off button.
    setFocusMode: function (active) {
      card.setAttribute("data-focus", active ? "true" : "false");
      waveOffBtn.hidden = !active;
    },
  };

  paint();
  function announceReady() {
    const a = api();
    if (a) a.ready();
  }
  window.addEventListener("pywebviewready", announceReady);
  setTimeout(announceReady, 800); // fallback if the event already fired
})();
