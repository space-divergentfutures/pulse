/* PULSE check-in + graph (spec §7).
 * Stage 1 (day 1–N): one tap in, the graph back immediately.
 * Stage 2 (after 5 ratings on 3+ days): rate → block-type context → graph.
 * Stage 3 (after 5 block-type fills): same + optional note textarea.
 * "Was this useful?" cadence fires every 5.5 accumulated active hours, Stage 2+ only.
 */
(function () {
  "use strict";

  const rateView    = document.getElementById("rateView");
  const contextView = document.getElementById("contextView");
  const usefulView  = document.getElementById("usefulView");
  const graphView   = document.getElementById("graphView");

  const scaleEl      = document.getElementById("scale");
  const skipBtn      = document.getElementById("skipBtn");
  const blockChips   = document.getElementById("blockChips");
  const noteField    = document.getElementById("noteField");
  const contextDone  = document.getElementById("contextDoneBtn");
  const contextSkip  = document.getElementById("contextSkipBtn");
  const chart        = document.getElementById("chart");
  const meterFill    = document.getElementById("meterFill");
  const meterLabel   = document.getElementById("meterLabel");
  const graphSub     = document.getElementById("graphSub");
  const patternsEl   = document.getElementById("patterns");
  const doneBtn      = document.getElementById("doneBtn");

  let _stage = 1;
  let _scaleMax = 10;
  let _selectedType = null;

  const BLOCK_TYPES = [
    { id: "deep",      label: "Deep work" },
    { id: "admin",     label: "Admin" },
    { id: "creative",  label: "Creative" },
    { id: "meetings",  label: "Meetings" },
    { id: "scattered", label: "Scattered" },
  ];

  function api() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
  }

  function escHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function show(view) {
    rateView.classList.toggle("hidden",    view !== "rate");
    contextView.classList.toggle("hidden", view !== "context");
    usefulView.classList.toggle("hidden",  view !== "useful");
    graphView.classList.toggle("hidden",   view !== "graph");
  }

  // --- rating scale -----------------------------------------------------------

  function buildScale(max) {
    scaleEl.innerHTML = "";
    for (let n = 1; n <= max; n++) {
      const b = document.createElement("button");
      b.className = "num";
      b.textContent = n;
      b.addEventListener("click", function () { onRate(n); });
      scaleEl.appendChild(b);
    }
  }

  async function onRate(n) {
    const a = api();
    if (!a) return;
    const data = await a.rate(n);
    afterRate(data, false);
  }

  function afterRate(data, skipped) {
    _stage = data.stage || 1;
    if (!skipped && _stage >= 2) {
      initContextView();
      show("context");
    } else {
      renderGraph(data);
      if (!skipped && data.useful_check_pending) {
        setTimeout(function () { show("useful"); }, 1400);
      }
    }
  }

  // --- context view (Stage 2/3) -----------------------------------------------

  function initContextView() {
    _selectedType = null;
    buildChips();
    noteField.classList.toggle("hidden", _stage < 3);
    noteField.value = "";
  }

  function buildChips() {
    blockChips.innerHTML = "";
    BLOCK_TYPES.forEach(function (bt) {
      const b = document.createElement("button");
      b.className = "chip";
      b.textContent = bt.label;
      b.dataset.id = bt.id;
      b.addEventListener("click", function () {
        _selectedType = bt.id;
        blockChips.querySelectorAll(".chip").forEach(function (c) {
          c.classList.toggle("sel", c.dataset.id === bt.id);
        });
      });
      blockChips.appendChild(b);
    });
  }

  contextDone.addEventListener("click", async function () {
    const a = api();
    if (!a) return;
    const note = (_stage >= 3 && noteField.value.trim()) ? noteField.value.trim() : null;
    const result = await a.submit_context(JSON.stringify({
      block_type: _selectedType,
      note: note,
    }));
    renderGraph(result);
    if (result.useful_check_pending) {
      setTimeout(function () { show("useful"); }, 1400);
    }
  });

  contextSkip.addEventListener("click", async function () {
    const a = api();
    if (!a) return;
    const result = await a.submit_context(JSON.stringify({ block_type: null, note: null }));
    renderGraph(result);
    if (result.useful_check_pending) {
      setTimeout(function () { show("useful"); }, 1400);
    }
  });

  // --- useful check view (§7) -------------------------------------------------

  document.querySelectorAll(".useful-btn").forEach(function (btn) {
    btn.addEventListener("click", async function () {
      const a = api();
      if (a) await a.useful_check(btn.dataset.response);
      show("graph");
    });
  });

  // --- graph view + patterns --------------------------------------------------

  function lerpHex(a, b, t) {
    const pa = [parseInt(a.slice(1,3),16), parseInt(a.slice(3,5),16), parseInt(a.slice(5,7),16)];
    const pb = [parseInt(b.slice(1,3),16), parseInt(b.slice(3,5),16), parseInt(b.slice(5,7),16)];
    const c = pa.map(function (v, i) { return Math.round(v + (pb[i] - v) * t); });
    return "rgb(" + c[0] + "," + c[1] + "," + c[2] + ")";
  }
  function ratingColour(rating, max) {
    const t = max > 1 ? (rating - 1) / (max - 1) : 0.5;
    return lerpHex("#6d9fd6", "#7fd1c1", t);
  }

  function renderGraph(data) {
    _scaleMax = data.scale_max || 10;
    const pts = data.points || [];

    const W = 300, H = 118, padX = 10, padTop = 10, padBot = 10;
    const innerW = W - padX * 2, innerH = H - padTop - padBot;
    const n = pts.length;

    let svg = '<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none">';
    for (let g = 0; g <= 4; g++) {
      const y = padTop + (innerH * g) / 4;
      svg += '<line x1="' + padX + '" y1="' + y + '" x2="' + (W - padX) + '" y2="' + y +
             '" stroke="rgba(255,255,255,0.06)" stroke-width="1"/>';
    }
    for (let i = 0; i < n; i++) {
      const p = pts[i];
      const x = n > 1 ? padX + (innerW * i) / (n - 1) : W / 2;
      const t = _scaleMax > 1 ? (p.rating - 1) / (_scaleMax - 1) : 0.5;
      const y = padTop + (1 - t) * innerH;
      const newest = i === n - 1;
      const col = ratingColour(p.rating, _scaleMax);
      if (newest) {
        svg += '<circle cx="' + x + '" cy="' + y + '" r="7" fill="none" stroke="' + col +
               '" stroke-width="2" opacity="0.5"/>';
      }
      svg += '<circle cx="' + x + '" cy="' + y + '" r="' + (newest ? 4.5 : 3.5) +
             '" fill="' + col + '"/>';
    }
    svg += "</svg>";
    chart.innerHTML = svg;

    if (n > 0) graphSub.textContent = "this block: " + pts[n - 1].rating + " / " + _scaleMax;

    meterFill.style.width = (data.meter_pct || 0) + "%";
    if (data.unlocked) {
      meterLabel.textContent = "pattern unlocked ✓ — your first insight is ready";
      meterLabel.classList.add("unlocked");
    } else {
      meterLabel.classList.remove("unlocked");
      meterLabel.textContent =
        data.count + "/" + data.floor + " check-ins \xb7 " + (data.meter_pct || 0) +
        "% to your first pattern";
    }

    const pats = data.patterns || [];
    if (pats.length > 0) {
      patternsEl.innerHTML = pats.map(function (p) {
        return '<p class="pattern-text">' + escHtml(p.text) + '</p>';
      }).join("");
      patternsEl.classList.remove("hidden");
    } else {
      patternsEl.innerHTML = "";
      patternsEl.classList.add("hidden");
    }

    show("graph");
  }

  // --- skip -------------------------------------------------------------------

  skipBtn.addEventListener("click", async function () {
    const a = api();
    if (!a) return;
    const data = await a.skip();
    renderGraph(data);
  });

  doneBtn.addEventListener("click", function () {
    const a = api();
    if (a) a.close();
  });

  // --- public API (called by Python via evaluate_js) --------------------------

  window.pulse = {
    startCheckin: function (stage, scaleMax) {
      _stage = stage || 1;
      _scaleMax = scaleMax || 10;
      buildScale(_scaleMax);
      show("rate");
    },
  };

  buildScale(_scaleMax);
  show("rate");

  function announceReady() {
    const a = api();
    if (a) a.ready();
  }
  window.addEventListener("pywebviewready", announceReady);
  setTimeout(announceReady, 800);
})();
