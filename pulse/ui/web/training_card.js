/* PULSE training card behaviour (spec §5b; Big Break menu v1).
 *
 * Phases (in order):
 *   getready          — 90 s countdown; user can skip to "I'm ready" or divert to Big Break
 *   session           — exercises shown one at a time; Done / Skip / Pain per exercise
 *   complete          — session done; level-up announcements; triggers check-in via Python
 *   bigbreak_pick     — all 5 presets (one tap → timer) + "Choose your own →"
 *   bigbreak_activity — custom path: grid of activities, cue shown on selection
 *   bigbreak_duration — custom path: scrollable duration picker, incl. open-ended
 *   bigbreak_timer    — countdown for a picked duration, or a counting-up stopwatch
 *                       for open-ended ("stop when I'm done")
 *
 * Python drives `window.pulse.startSession(data)`.
 * JS calls back into Python via `pywebview.api.*`.
 */
(function () {
  "use strict";

  /* --- element refs -------------------------------------------------------- */
  const phases = {
    getready:       document.getElementById("phaseGetready"),
    session:        document.getElementById("phaseSession"),
    complete:       document.getElementById("phaseComplete"),
    bigbreak_pick:  document.getElementById("phaseBigPick"),
    bigbreak_activity: document.getElementById("phaseBigActivity"),
    bigbreak_duration: document.getElementById("phaseBigDuration"),
    bigbreak_timer: document.getElementById("phaseBigTimer"),
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

  // big break — preset/choose-own picker
  const bigOptions = document.getElementById("bigOptions");

  // big break — activity grid (custom path)
  const bigActivityGrid = document.getElementById("bigActivityGrid");
  const bigActivityCue  = document.getElementById("bigActivityCue");
  const bigActivityNext = document.getElementById("bigActivityNext");
  const bigActivityBack = document.getElementById("bigActivityBack");

  // big break — duration picker (custom path)
  const bigDurationName   = document.getElementById("bigDurationName");
  const bigDurationSelect = document.getElementById("bigDurationSelect");
  const bigDurationStart  = document.getElementById("bigDurationStart");
  const bigDurationBack   = document.getElementById("bigDurationBack");

  // big break — timer (countdown or stopwatch)
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
  let bigTimerMode   = "countdown";  // "countdown" | "stopwatch" (open-ended)
  let bigTimerStartAt= null;         // stopwatch mode: when it started
  let currentBigBreak= null;         // {activityId, name, description, cue,
                                      //  durationMinutes, openEnded, hardLock, presetId}
  let selectedActivity = null;       // custom path: activity chosen in the grid
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
    if (currentPhase === "bigbreak_timer") {
      if (bigTimerMode === "stopwatch") {
        bigTimer.textContent = fmt((Date.now() - bigTimerStartAt) / 1000);
      } else if (bigTimerEndAt) {
        const left = (bigTimerEndAt - Date.now()) / 1000;
        bigTimer.textContent = fmt(left);
        if (left <= 0 && !bigTimerFired) {
          bigTimerFired = true;
          bigTimer.textContent = "0:00";
          bigDone.disabled = false;
        }
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

  /* --- big break: preset picker + "choose your own" ------------------------ */
  function showBigBreakPicker() {
    bigOptions.innerHTML = "";
    const presets = data.presets || [];
    presets.forEach(function (p) {
      const btn = document.createElement("button");
      btn.className = "big-option-btn" + (p.available ? "" : " unavailable");
      btn.disabled = !p.available;
      btn.innerHTML = p.name +
        (p.rainOk ? '<span class="rain">(indoor OK)</span>' : "") +
        (p.available ? "" : '<span class="reason">' + p.reason + "</span>");
      if (p.available) {
        btn.addEventListener("click", function () {
          confirmBigBreak({
            activityId: p.activityId, presetId: p.id, name: p.name,
            description: p.description, cue: p.cue,
            durationMinutes: p.durationMinutes, openEnded: false,
            hardLock: p.hardLock,
          });
        });
      }
      bigOptions.appendChild(btn);
    });

    const chooseOwn = document.createElement("button");
    chooseOwn.className = "big-option-btn choose-own";
    chooseOwn.textContent = "Choose your own →";
    chooseOwn.addEventListener("click", showBigActivityPicker);
    bigOptions.appendChild(chooseOwn);

    showPhase("bigbreak_pick");
  }

  /* --- big break: activity grid (custom path) ------------------------------ */
  function showBigActivityPicker() {
    selectedActivity = null;
    bigActivityNext.disabled = true;
    bigActivityCue.innerHTML = "&nbsp;";
    bigActivityGrid.innerHTML = "";
    const activities = data.activities || [];
    activities.forEach(function (act) {
      const btn = document.createElement("button");
      btn.className = "big-activity-btn";
      btn.textContent = act.name;
      btn.disabled = !act.available;
      if (!act.available) btn.title = act.reason;
      btn.addEventListener("click", function () {
        selectedActivity = act;
        bigActivityGrid.querySelectorAll(".big-activity-btn").forEach(function (b) {
          b.classList.toggle("selected", b === btn);
        });
        bigActivityCue.textContent = act.cue;
        bigActivityNext.disabled = false;
      });
      bigActivityGrid.appendChild(btn);
    });
    showPhase("bigbreak_activity");
  }

  bigActivityNext.addEventListener("click", function () {
    if (selectedActivity) showBigDurationPicker(selectedActivity);
  });
  bigActivityBack.addEventListener("click", showBigBreakPicker);

  /* --- big break: duration picker (custom path) ----------------------------- */
  function showBigDurationPicker(activity) {
    bigDurationName.textContent = activity.name;
    bigDurationSelect.innerHTML = "";
    const options = data.durationOptions || [];
    options.forEach(function (o, idx) {
      const opt = document.createElement("option");
      opt.value = idx;
      opt.textContent = o.label;
      if (o.minutes === activity.defaultMinutes) opt.selected = true;
      bigDurationSelect.appendChild(opt);
    });
    showPhase("bigbreak_duration");
  }

  bigDurationBack.addEventListener("click", function () {
    showBigActivityPicker();
  });

  bigDurationStart.addEventListener("click", function () {
    const idx = parseInt(bigDurationSelect.value, 10);
    const chosen = (data.durationOptions || [])[idx];
    if (!chosen || !selectedActivity) return;
    const openEnded = chosen.minutes === null;
    const hardLock = !openEnded &&
      data.hardLockEnabled &&
      chosen.minutes <= data.hardlockCeilingMinutes;
    confirmBigBreak({
      activityId: selectedActivity.id, presetId: null,
      name: selectedActivity.name, description: "", cue: selectedActivity.cue,
      durationMinutes: chosen.minutes, openEnded: openEnded, hardLock: hardLock,
    });
  });

  /* --- big break: confirm + timer (countdown or stopwatch) ------------------ */
  function confirmBigBreak(opts) {
    currentBigBreak = opts;
    bigName.textContent = opts.name;
    bigDesc.textContent = opts.description || "";
    bigCue.textContent  = opts.cue || "";

    if (opts.openEnded) {
      bigTimerMode    = "stopwatch";
      bigTimerStartAt = Date.now();
      bigTimer.textContent = "0:00";
      bigDone.disabled = false;  // open-ended is never hard-locked
    } else {
      bigTimerMode     = "countdown";
      bigTimerFired     = false;
      bigTimerEndAt     = Date.now() + opts.durationMinutes * 60 * 1000;
      bigTimer.textContent = fmt(opts.durationMinutes * 60);
      // Honor-based unless this specific session is hard-lock eligible.
      bigDone.disabled = !!opts.hardLock;
    }
    showPhase("bigbreak_timer");
    const a = api();
    if (a) a.big_break_started(opts.activityId);
  }

  bigDone.addEventListener("click", function () {
    const a = api();
    if (!a || !currentBigBreak) return;
    const elapsedMinutes = bigTimerMode === "stopwatch"
      ? (Date.now() - bigTimerStartAt) / 60000
      : currentBigBreak.durationMinutes;
    a.big_break_done(currentBigBreak.activityId, elapsedMinutes, currentBigBreak.openEnded);
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
