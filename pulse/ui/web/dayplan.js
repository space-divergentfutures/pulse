/* PULSE day plan card behaviour (reading feature).
 *
 * One question at the first active moment of the day: how long are you here?
 * +/- picker in half-hour steps. "Start my day" sends the hours to Python;
 * "not today" skips without guilt. Python owns what happens next (scheduling
 * the reading session at the midpoint if the day is long enough).
 */
(function () {
  "use strict";

  const planNum   = document.getElementById("planNum");
  const planMinus = document.getElementById("planMinus");
  const planPlus  = document.getElementById("planPlus");
  const planStart = document.getElementById("planStart");
  const planSkip  = document.getElementById("planSkip");

  const pick = { val: 4.0, min: 0.5, max: 12.0, step: 0.5 };

  function api() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
  }

  function fmt(hours) {
    // 4 → "4", 4.5 → "4½" — reads like speech, not like a spreadsheet
    const whole = Math.floor(hours);
    const half = hours - whole >= 0.5;
    if (whole === 0) return "½";
    return half ? whole + "½" : String(whole);
  }

  function paint() { planNum.textContent = fmt(pick.val); }

  planMinus.addEventListener("click", function () {
    if (pick.val > pick.min) { pick.val -= pick.step; paint(); }
  });

  planPlus.addEventListener("click", function () {
    if (pick.val < pick.max) { pick.val += pick.step; paint(); }
  });

  planStart.addEventListener("click", function () {
    const a = api();
    if (a) a.plan_day(pick.val);
  });

  planSkip.addEventListener("click", function () {
    const a = api();
    if (a) a.skip_day_plan();
  });

  /* --- the interface Python drives -------------------------------------- */
  window.pulse = {
    // Reset the picker before the card is shown (default from settings later).
    reset: function (defaultHours) {
      pick.val = defaultHours || 4.0;
      paint();
    },
  };

  paint();
  function announceReady() {
    const a = api();
    if (a) a.ready();
  }
  window.addEventListener("pywebviewready", announceReady);
  setTimeout(announceReady, 800);
})();
