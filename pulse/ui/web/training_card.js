/* PULSE training card behaviour (spec §5b).
 *
 * Phases (in order):
 *   getready      — 90 s countdown; user can skip to "I'm ready" or divert to Big Break
 *   session       — exercises shown one at a time; Done / Skip / Pain per exercise
 *   complete      — session done; level-up announcements; triggers check-in via Python
 *   bigbreak_pick — Big Break option picker
 *   bigbreak_timer — 12-min wall-clock timer for chosen option
 *
 * Python drives `window.pulse.startSession(data)`.
 * JS calls back into Python via `pywebview.api.*`.
 */
(function () {
  "use strict";

  /* --- element refs -------------------------------------------------------- */
  const phases = {
    getready:      document.getElementById("phaseGetready"),
    session:       document.getElementById("phaseSession"),
    complete:      document.getElementById("phaseComplete"),
    bigbreak_pick: document.getElementById("phaseBigPick"),
    bigbreak_timer:document.getElementById("phaseBigTimer"),
  };

  // get-ready
  const grKicker  = document.getElementById("grKicker");
  const grSession = document.getElementById("grSession");
  const grTimer   = document.getElementById("grTimer");
  const grReady   = document.getElementById("grReady");
  const grBigBreak= document.getElementById("grBigBreak");

  // session
  const sessProgress = document.getElementById("sessProgress");
  const sessName     = document.getElementById("sessName");
  const sessLevel    = document.getElementById("sessLevel");
  const sessWork     = document.getElementById("sessWork");
  const sessCue      = document.getElementById("sessCue");
  const sessTimerRow = document.getElementById("sessTimerRow");
  const sessTimer    = document.getElementById("sessTimer");
  const sessDone     = document.getElementById("sessDone");
  const sessSkip     = document.getElementById("sessSkip");
  const sessPain     = document.getElementById("sessPain");

  // complete
  const completeMsg   = document.getElementById("completeMsg");
  const completeClose = document.getElementById("completeClose");

  // big break
  const bigOptions = document.getElementById("bigOptions");
  const bigName    = document.getElementById("bigName");
  const bigDesc    = document.getElementById("bigDesc");
  const bigCue     = document.getElementById("bigCue");
  const bigTimer   = document.getElementById("bigTimer");
  const bigDone    = document.getElementById("bigDone");

  /* --- state --------------------------------------------------------------- */
  let data           = null;   // full payload from startSession()
  let exercises      = [];     // array of exercise objects (training only)
  let exIdx          = 0;      // current exercise index
  let outcomes       = [];     // {id, outcome, level_changed, new_level} per exercise
  let grTimerEndAt   = null;
  let bigTimerEndAt  = null;
  let bigTimerFired  = false;
  let sessTimerEndAt = null;
  let sessTimerFired = false;
  let currentPhase   = null;

  function api() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
  }

  function fmt(sec) {
    sec = Math.max(0, Math.round(sec));
    return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0");
  }

  function showPhase(name) {
    Object.keys(phases).forEach(k => { phases[k].hidden = (k !== name); });
    currentPhase = name;
  }

  /* --- get-ready timer ---------------------------------------------------- */
  setInterval(function () {
    if (currentPhase === "getready" && grTimerEndAt) {
      const left = (grTimerEndAt - Date.now()) / 1000;
      grTimer.textContent = fmt(left);
      if (left <= 0) {
        grTimerEndAt = null;
        startSession();
      }
    }
    if (currentPhase === "session" && sessTimerEndAt) {
      const left = (sessTimerEndAt - Date.now()) / 1000;
      sessTimer.textContent = fmt(left);
      if (left <= 0 && !sessTimerFired) {
        sessTimerFired = true;
        sessTimer.textContent = "0:00";
        sessDone.disabled = false;
      }
    }
    if (currentPhase === "bigbreak_timer" && bigTimerEndAt) {
      const left = (bigTimerEndAt - Date.now()) / 1000;
      bigTimer.textContent = fmt(left);
      if (left <= 0 && !bigTimerFired) {
        bigTimerFired = true;
        bigTimer.textContent = "0:00";
        bigDone.disabled = false;
      }
    }
  }, 1000);

  /* --- get-ready phase ---------------------------------------------------- */
  grReady.addEventListener("click", function () {
    grTimerEndAt = null;
    startSession();
  });

  grBigBreak.addEventListener("click", function () {
    grTimerEndAt = null;
    showBigBreakPicker();
  });

  /* --- session phase ------------------------------------------------------- */
  function showExercise(idx) {
    const ex = exercises[idx];
    sessProgress.textContent = "Exercise " + (idx + 1) + " of " + exercises.length;
    sessName.textContent     = ex.name;
    sessLevel.textContent    = "L" + ex.level;
    sessWork.textContent     = ex.work;
    sessCue.textContent      = ex.cue;

    // Timed exercise: show timer, disable Done until it fires
    sessTimerFired  = false;
    sessTimerEndAt  = null;
    if (ex.duration_s) {
      sessTimerRow.hidden   = false;
      sessTimer.textContent = fmt(ex.duration_s);
      sessTimerEndAt        = Date.now() + ex.duration_s * 1000;
      sessDone.disabled     = true;
    } else {
      sessTimerRow.hidden = true;
      sessDone.disabled   = false;
    }

    if (data.hardLock) {
      sessSkip.style.display = "none";
    }
    showPhase("session");
  }

  function advanceSession(outcome, extraData) {
    const ex = exercises[exIdx];
    outcomes.push(Object.assign({ id: ex.id, outcome: outcome }, extraData || {}));
    const a = api();
    if (a) {
      if (outcome === "done")  a.exercise_done(ex.id);
      if (outcome === "skip")  a.exercise_skip(ex.id);
      if (outcome === "pain")  a.exercise_pain(ex.id);
    }
    exIdx++;
    if (exIdx < exercises.length) {
      showExercise(exIdx);
    } else {
      showComplete();
    }
  }

  sessDone.addEventListener("click", function () { advanceSession("done"); });
  sessSkip.addEventListener("click", function () { advanceSession("skip"); });
  sessPain.addEventListener("click", function () { advanceSession("pain"); });

  /* --- complete phase ------------------------------------------------------ */
  function showComplete() {
    // Build message from outcomes (level changes)
    const lines = outcomes
      .filter(o => o.level_changed)
      .map(o => "Level " + o.new_level + " unlocked for " + o.id.replace(/_/g, " ") + " 🎉");
    completeMsg.textContent = lines.length
      ? lines.join("\n")
      : "Every session is a deposit.";
    showPhase("complete");
    const a = api();
    if (a) a.session_complete(JSON.stringify(outcomes));
  }

  completeClose.addEventListener("click", function () {
    const a = api();
    if (a) a.close_card();
  });

  /* --- big break picker ---------------------------------------------------- */
  function showBigBreakPicker() {
    bigOptions.innerHTML = "";
    const options = data.options || [];
    options.forEach(function (opt) {
      const btn = document.createElement("button");
      btn.className = "big-option-btn";
      btn.innerHTML = opt.name +
        (opt.rain_ok ? '<span class="rain">(indoor OK)</span>' : "");
      btn.addEventListener("click", function () { startBigBreak(opt); });
      bigOptions.appendChild(btn);
    });
    showPhase("bigbreak_pick");
  }

  function startBigBreak(opt) {
    bigName.textContent  = opt.name;
    bigDesc.textContent  = opt.description;
    bigCue.textContent   = opt.cue;
    bigTimer.textContent = fmt(opt.duration_s);
    bigTimerFired        = false;
    bigTimerEndAt        = Date.now() + opt.duration_s * 1000;
    bigDone.disabled     = false;  // honor-based — user can always end early
    showPhase("bigbreak_timer");
    const a = api();
    if (a) a.big_break_started(opt.id);
  }

  bigDone.addEventListener("click", function () {
    const a = api();
    if (a) a.big_break_done();
  });

  /* --- session start (after get-ready) ------------------------------------ */
  function startSession() {
    if (data.type === "training") {
      exercises = data.exercises || [];
      exIdx     = 0;
      outcomes  = [];
      showExercise(0);
    } else if (data.type === "big_break") {
      showBigBreakPicker();
    }
  }

  /* --- public API --------------------------------------------------------- */
  window.pulse = {
    startSession: function (d) {
      data = d;
      exIdx = 0; outcomes = [];

      if (d.type === "training") {
        // Build exercise list for get-ready summary
        grKicker.textContent = "Training break";
        grSession.innerHTML = (d.exercises || []).map(function (ex) {
          return '<div class="gr-ex">' +
            '<span class="gr-ex-name">' + ex.name + '</span>' +
            '<span class="gr-ex-meta">L' + ex.level + ' · ' + ex.work + '</span>' +
            '</div>';
        }).join("");
        grTimerEndAt = Date.now() + 90 * 1000;
        grTimer.textContent = "1:30";
        showPhase("getready");
      } else if (d.type === "big_break") {
        // Big Break shortcut: skip get-ready, go straight to picker
        showBigBreakPicker();
      }
    },
  };

  /* --- ready handshake ---------------------------------------------------- */
  function announceReady() {
    const a = api();
    if (a) a.ready();
  }
  window.addEventListener("pywebviewready", announceReady);
  setTimeout(announceReady, 800);
})();
