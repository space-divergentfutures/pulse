/* PULSE light break card behaviour (spec §5a, §5d).
 *
 * Two phases live in the same window:
 *   1. Meal question (shown if data.mealPrompt is true) — "Have you eaten today?"
 *      Yes → normal break.  Not yet → duration picker → food break.  Not now → deferred.
 *   2. Normal break — movement name/detail, hydration, self-started timer, Done button.
 *
 * The break timer is wall-clock and JS-owned — you started it. When it reaches zero the
 * card doesn't vanish or nag; it just says you're good to head back.
 */
(function () {
  "use strict";

  /* --- elements ----------------------------------------------------------- */
  const mealPhase       = document.getElementById("mealPhase");
  const mealQuestion    = document.getElementById("mealQuestion");
  const mealPicker      = document.getElementById("mealPicker");
  const mealDetail      = document.getElementById("mealDetail");
  const mealYes         = document.getElementById("mealYes");
  const mealNo          = document.getElementById("mealNo");
  const mealDefer       = document.getElementById("mealDefer");
  const mealGo          = document.getElementById("mealGo");
  const mealSkip        = document.getElementById("mealSkip");
  const mealDetailDone  = document.getElementById("mealDetailDone");
  const mealDetailSkip  = document.getElementById("mealDetailSkip");
  const pickMinus       = document.getElementById("pickMinus");
  const pickPlus        = document.getElementById("pickPlus");
  const pickNum         = document.getElementById("pickNum");

  const breakContent = document.getElementById("breakContent");
  const kicker       = document.getElementById("kicker");
  const timerEl      = document.getElementById("timer");
  const moveName     = document.getElementById("moveName");
  const moveDetail   = document.getElementById("moveDetail");
  const hydrateText  = document.getElementById("hydrateText");
  const doneBtn      = document.getElementById("doneBtn");
  const honor        = document.getElementById("honor");

  /* --- state -------------------------------------------------------------- */
  const timer = { endAt: null, fired: false, running: false };
  const pick  = { val: 20, min: 10, max: 45 };
  let pending      = null;  // the data object from the last startBreak() call
  let selectedFood  = null;
  let selectedWater = null;

  function api() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
  }

  function fmt(sec) {
    sec = Math.max(0, Math.round(sec));
    return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0");
  }

  /* --- timer tick --------------------------------------------------------- */
  setInterval(function () {
    if (!timer.running) return;
    const left = (timer.endAt - Date.now()) / 1000;
    timerEl.textContent = fmt(left);
    if (left <= 0 && !timer.fired) {
      timer.fired = true;
      timerEl.textContent = "0:00";
      honor.textContent = "nice — head back whenever you're ready";
      const a = api();
      if (a) a.timer_finished();
    }
  }, 1000);

  /* --- show the normal break (called once meal question is resolved) ------ */
  function showBreak(overrideSeconds) {
    const data = pending;
    if (!data) return;

    kicker.textContent = overrideSeconds && overrideSeconds !== data.seconds
      ? "Food break"
      : (data.kicker || "Light break");
    moveName.textContent    = data.name     || "";
    moveDetail.textContent  = data.detail   || "";
    hydrateText.textContent = data.hydration || "water within reach?";
    honor.textContent       = data.honor    || "move if you can — it’s yours, do it your way";

    const secs = overrideSeconds || data.seconds || 90;
    timer.endAt   = Date.now() + secs * 1000;
    timer.fired   = false;
    timer.running = true;
    timerEl.textContent = fmt(secs);

    mealPhase.hidden    = true;
    breakContent.hidden = false;
  }

  /* --- meal phase handlers ------------------------------------------------ */
  mealYes.addEventListener("click", function () {
    selectedFood  = null;
    selectedWater = null;
    mealDetail.querySelectorAll(".chip").forEach(function (c) { c.classList.remove("selected"); });
    mealQuestion.hidden = true;
    mealDetail.hidden   = false;
  });

  document.getElementById("foodChips").addEventListener("click", function (e) {
    var chip = e.target.closest(".chip");
    if (!chip) return;
    selectedFood = chip.dataset.val;
    this.querySelectorAll(".chip").forEach(function (c) {
      c.classList.toggle("selected", c.dataset.val === selectedFood);
    });
  });

  document.getElementById("waterChips").addEventListener("click", function (e) {
    var chip = e.target.closest(".chip");
    if (!chip) return;
    selectedWater = chip.dataset.val;
    this.querySelectorAll(".chip").forEach(function (c) {
      c.classList.toggle("selected", c.dataset.val === selectedWater);
    });
  });

  mealDetailDone.addEventListener("click", function () {
    try { const a = api(); if (a) a.meal_yes(selectedFood, selectedWater); } catch (_) {}
    showBreak();
  });

  mealDetailSkip.addEventListener("click", function () {
    try { const a = api(); if (a) a.meal_yes(null, null); } catch (_) {}
    showBreak();
  });

  mealNo.addEventListener("click", function () {
    mealQuestion.hidden = true;
    mealPicker.hidden   = false;
    pickNum.textContent = pick.val;
  });

  mealDefer.addEventListener("click", function () {
    try { const a = api(); if (a) a.meal_deferred(); } catch (_) {}
    showBreak();
  });

  mealSkip.addEventListener("click", function () {
    try { const a = api(); if (a) a.meal_deferred(); } catch (_) {}
    showBreak();
  });

  pickMinus.addEventListener("click", function () {
    if (pick.val > pick.min) { pick.val -= 5; pickNum.textContent = pick.val; }
  });

  pickPlus.addEventListener("click", function () {
    if (pick.val < pick.max) { pick.val += 5; pickNum.textContent = pick.val; }
  });

  mealGo.addEventListener("click", function () {
    var mins = pick.val;
    try { const a = api(); if (a) a.meal_no(mins); } catch (_) {}
    showBreak(mins * 60);
  });

  /* --- normal break Done button ------------------------------------------- */
  doneBtn.addEventListener("click", function () {
    const a = api();
    if (a) a.done();
  });

  /* --- public API --------------------------------------------------------- */
  window.pulse = {
    startBreak: function (data) {
      pending = data;

      // Reset timer state for new break
      timer.running = false;
      timer.fired   = false;

      if (data.mealPrompt) {
        // Set up picker defaults from Python-supplied range
        pick.min = data.mealMin || 10;
        pick.max = data.mealMax || 45;
        pick.val = data.mealDefault || 20;
        pickNum.textContent = pick.val;

        // Show meal question, hide picker, detail, and break content
        mealQuestion.hidden = false;
        mealPicker.hidden   = true;
        mealDetail.hidden   = true;
        selectedFood        = null;
        selectedWater       = null;
        mealPhase.hidden    = false;
        breakContent.hidden = true;
      } else {
        mealPhase.hidden = true;
        showBreak();
      }
    },
  };

  /* --- announce ready ----------------------------------------------------- */
  function announceReady() {
    const a = api();
    if (a) a.ready();
  }
  window.addEventListener("pywebviewready", announceReady);
  setTimeout(announceReady, 800);
})();
