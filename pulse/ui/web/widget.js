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

  const state = {
    phase: "countdown",   // countdown | due | timer | done | training
    remaining: 0,         // seconds
    timerEndAt: null,     // ms epoch, for the self-started timer
    timerFired: false,
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
    }
  }

  // One heartbeat drives the visible tick for both clocks.
  setInterval(function () {
    if (state.phase === "countdown" || state.phase === "due") {
      if (state.remaining > 0) state.remaining -= 1; // smooth between Python re-syncs
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
    if (state.phase === "countdown" || state.phase === "due") {
      if (a) a.break_now();
    } else {
      if (a) a.done();
    }
  });

  // --- the interface Python drives via evaluate_js ---
  window.pulse = {
    // ACTIVE-time countdown; escalated => the mark has passed (phase "due").
    showCountdown: function (remainingSeconds, escalated) {
      state.phase = escalated ? "due" : "countdown";
      state.remaining = remainingSeconds;
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
  };

  paint();
  function announceReady() {
    const a = api();
    if (a) a.ready();
  }
  window.addEventListener("pywebviewready", announceReady);
  setTimeout(announceReady, 800); // fallback if the event already fired
})();
