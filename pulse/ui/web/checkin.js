/* PULSE check-in + graph (spec §7).
 * One tap in, the graph back immediately. Dots from day 1 (unlabelled — the interpretation
 * layer unlocks later, §7/§10); the meter shows honest progress toward the evidence floor.
 */
(function () {
  "use strict";

  const rateView = document.getElementById("rateView");
  const graphView = document.getElementById("graphView");
  const scaleEl = document.getElementById("scale");
  const skipBtn = document.getElementById("skipBtn");
  const doneBtn = document.getElementById("doneBtn");
  const chart = document.getElementById("chart");
  const meterFill = document.getElementById("meterFill");
  const meterLabel = document.getElementById("meterLabel");
  const graphSub = document.getElementById("graphSub");

  let scaleMax = 10;

  function api() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
  }

  function show(view) {
    rateView.classList.toggle("hidden", view !== "rate");
    graphView.classList.toggle("hidden", view !== "graph");
  }

  function buildScale(max) {
    scaleEl.innerHTML = "";
    for (let n = 1; n <= max; n++) {
      const b = document.createElement("button");
      b.className = "num";
      b.textContent = n;
      b.addEventListener("click", async function () {
        const a = api();
        if (!a) return;
        const data = await a.rate(n);
        renderGraph(data);
      });
      scaleEl.appendChild(b);
    }
  }

  // --- colour: calm blue (low) -> teal (high). No judgmental red/green. ---
  function lerpHex(a, b, t) {
    const pa = [parseInt(a.slice(1, 3), 16), parseInt(a.slice(3, 5), 16), parseInt(a.slice(5, 7), 16)];
    const pb = [parseInt(b.slice(1, 3), 16), parseInt(b.slice(3, 5), 16), parseInt(b.slice(5, 7), 16)];
    const c = pa.map((v, i) => Math.round(v + (pb[i] - v) * t));
    return "rgb(" + c[0] + "," + c[1] + "," + c[2] + ")";
  }
  function ratingColour(rating, max) {
    const t = max > 1 ? (rating - 1) / (max - 1) : 0.5;
    return lerpHex("#6d9fd6", "#7fd1c1", t);
  }

  function renderGraph(data) {
    scaleMax = data.scale_max || 10;
    const pts = data.points || [];

    const W = 300, H = 118, padX = 10, padTop = 10, padBot = 10;
    const innerW = W - padX * 2, innerH = H - padTop - padBot;
    const n = pts.length;

    let svg = '<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none">';
    // faint gridlines at the scale quartiles
    for (let g = 0; g <= 4; g++) {
      const y = padTop + (innerH * g) / 4;
      svg += '<line x1="' + padX + '" y1="' + y + '" x2="' + (W - padX) + '" y2="' + y +
             '" stroke="rgba(255,255,255,0.06)" stroke-width="1"/>';
    }
    // dots
    for (let i = 0; i < n; i++) {
      const p = pts[i];
      const x = n > 1 ? padX + (innerW * i) / (n - 1) : W / 2;
      const t = scaleMax > 1 ? (p.rating - 1) / (scaleMax - 1) : 0.5;
      const y = padTop + (1 - t) * innerH;
      const newest = i === n - 1;
      const col = ratingColour(p.rating, scaleMax);
      if (newest) {
        svg += '<circle cx="' + x + '" cy="' + y + '" r="7" fill="none" stroke="' + col +
               '" stroke-width="2" opacity="0.5"/>';
      }
      svg += '<circle cx="' + x + '" cy="' + y + '" r="' + (newest ? 4.5 : 3.5) +
             '" fill="' + col + '"/>';
    }
    svg += "</svg>";
    chart.innerHTML = svg;

    if (n > 0) graphSub.textContent = "this block: " + pts[n - 1].rating + " / " + scaleMax;

    // unlock meter — honest progress toward the floor
    meterFill.style.width = (data.meter_pct || 0) + "%";
    if (data.unlocked) {
      meterLabel.textContent = "pattern unlocked ✓ — your first insight is ready";
      meterLabel.classList.add("unlocked");
    } else {
      meterLabel.classList.remove("unlocked");
      meterLabel.textContent =
        data.count + "/" + data.floor + " check-ins · " + (data.meter_pct || 0) +
        "% to your first pattern";
    }
    show("graph");
  }

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

  window.pulse = {
    startCheckin: function (max) {
      scaleMax = max || 10;
      buildScale(scaleMax);
      show("rate");
    },
  };

  buildScale(scaleMax);
  show("rate");

  function announceReady() {
    const a = api();
    if (a) a.ready();
  }
  window.addEventListener("pywebviewready", announceReady);
  setTimeout(announceReady, 800);
})();
