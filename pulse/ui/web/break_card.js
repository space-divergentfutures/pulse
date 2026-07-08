/* PULSE light break card behaviour (spec §5a, §5d).
 * The self-started movement timer is wall-clock and JS-owned — you started it. When it
 * reaches zero the card doesn't vanish or nag; it just says you're good to head back.
 */
(function () {
  "use strict";

  const kicker = document.getElementById("kicker");
  const timerEl = document.getElementById("timer");
  const moveName = document.getElementById("moveName");
  const moveDetail = document.getElementById("moveDetail");
  const hydrateText = document.getElementById("hydrateText");
  const doneBtn = document.getElementById("doneBtn");
  const honor = document.getElementById("honor");

  const state = { endAt: null, fired: false, running: false };

  function api() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
  }

  function fmt(sec) {
    sec = Math.max(0, Math.round(sec));
    return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0");
  }

  setInterval(function () {
    if (!state.running) return;
    const left = (state.endAt - Date.now()) / 1000;
    timerEl.textContent = fmt(left);
    if (left <= 0 && !state.fired) {
      state.fired = true;
      timerEl.textContent = "0:00";
      honor.textContent = "nice — head back whenever you're ready";
      const a = api();
      if (a) a.timer_finished();
    }
  }, 1000);

  doneBtn.addEventListener("click", function () {
    const a = api();
    if (a) a.done();
  });

  window.pulse = {
    startBreak: function (data) {
      kicker.textContent = data.kicker || "Light break";
      moveName.textContent = data.name || "";
      moveDetail.textContent = data.detail || "";
      hydrateText.textContent = data.hydration || "water within reach?";
      honor.textContent = data.honor || "move if you can — it's yours, do it your way";
      state.endAt = Date.now() + (data.seconds || 90) * 1000;
      state.fired = false;
      state.running = true;
      timerEl.textContent = fmt(data.seconds || 90);
    },
  };

  function announceReady() {
    const a = api();
    if (a) a.ready();
  }
  window.addEventListener("pywebviewready", announceReady);
  setTimeout(announceReady, 800);
})();
