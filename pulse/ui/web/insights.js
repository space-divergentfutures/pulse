/* PULSE Insights (spec §7/§10).
 * Pre-floor: unlabelled dots + progress meter ("building your picture").
 * At 100%: pattern cards reveal, week chart gains meaning, title changes.
 * No clinical labels. No placements. Hedged language only.
 */
(function () {
  "use strict";

  function api() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
  }
  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // --- load + render ----------------------------------------------------------

  async function load() {
    const a = api();
    if (!a) return;
    const data = await a.load();
    render(data);
  }

  function render(data) {
    renderHeader(data);
    renderMeter(data);
    renderWeekChart(data);
    renderPatterns(data);
    renderStage(data);
    renderStats(data);
  }

  // --- header -----------------------------------------------------------------

  function renderHeader(data) {
    const title = document.getElementById("insTitle");
    const sub   = document.getElementById("insSub");
    if (data.unlocked) {
      title.textContent = "Your patterns";
      sub.textContent   = "Here are your rhythms — honest, floor-gated.";
    } else {
      title.textContent = "Building your picture";
      sub.textContent   = "Every check-in moves the bar.";
    }
  }

  // --- main unlock meter ------------------------------------------------------

  function renderMeter(data) {
    const fill    = document.getElementById("meterFill");
    const pctEl   = document.getElementById("meterPct");
    const caption = document.getElementById("meterCaption");
    const detail  = document.getElementById("meterDetail");

    const pct = data.meter_pct || 0;
    fill.style.width = pct + "%";
    pctEl.textContent = pct + "%";

    if (data.unlocked) {
      caption.textContent = "Pattern floor";
      detail.textContent  = "Evidence floor met — patterns are honest.";
      detail.classList.add("unlocked");
    } else {
      caption.textContent = "Progress to first pattern";
      detail.classList.remove("unlocked");
      detail.textContent  =
        data.count + " / " + data.floor +
        " check-ins · " + pct + "% to your first pattern";
    }
  }

  // --- week dot chart ---------------------------------------------------------

  function lerpHex(a, b, t) {
    const pa = [parseInt(a.slice(1,3),16), parseInt(a.slice(3,5),16), parseInt(a.slice(5,7),16)];
    const pb = [parseInt(b.slice(1,3),16), parseInt(b.slice(3,5),16), parseInt(b.slice(5,7),16)];
    const c  = pa.map(function(v,i){ return Math.round(v+(pb[i]-v)*t); });
    return "rgb("+c[0]+","+c[1]+","+c[2]+")";
  }
  function ratingColour(r, max) {
    return lerpHex("#6d9fd6", "#7fd1c1", max > 1 ? (r-1)/(max-1) : 0.5);
  }

  function renderWeekChart(data) {
    const el     = document.getElementById("weekChart");
    const subEl  = document.getElementById("weekSub");
    const days   = data.week_days || [];
    const max    = data.scale_max || 10;
    const W      = 420, H = 120;
    const padL   = 4, padR = 4, padTop = 8, padBot = 24;
    const cols   = days.length || 7;
    const colW   = (W - padL - padR) / cols;
    const innerH = H - padTop - padBot;

    let svg = '<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none">';

    // gridlines
    for (let g = 0; g <= 4; g++) {
      const y = padTop + (innerH * g) / 4;
      svg += '<line x1="' + padL + '" y1="' + y + '" x2="' + (W - padR) + '" y2="' + y +
             '" stroke="rgba(255,255,255,0.05)" stroke-width="1"/>';
    }

    days.forEach(function (d, i) {
      const cx = padL + (i + 0.5) * colW;
      const labelY = H - 5;
      const isFuture = d.future;

      // day label
      const labelColour = d.today
        ? "var(--accent)"
        : (isFuture ? "rgba(255,255,255,0.15)" : "rgba(255,255,255,0.45)");
      svg += '<text x="' + cx + '" y="' + labelY + '" text-anchor="middle" ' +
             'font-size="10" fill="' + labelColour + '">' + esc(d.day) + '</text>';

      if (!isFuture && d.ratings && d.ratings.length > 0) {
        // dots — spread horizontally by ±jitter within the column so they don't stack
        const jMax = Math.min(colW * 0.3, 8);
        d.ratings.forEach(function (r, ri) {
          const t    = (max > 1) ? (r - 1) / (max - 1) : 0.5;
          const y    = padTop + (1 - t) * innerH;
          const jit  = d.ratings.length > 1
            ? (ri / (d.ratings.length - 1) - 0.5) * jMax * 2
            : 0;
          const col  = ratingColour(r, max);
          svg += '<circle cx="' + (cx + jit) + '" cy="' + y + '" r="3.5" fill="' + col + '"/>';
        });

        // average tick — small horizontal line across the column
        if (d.avg !== null && d.avg !== undefined) {
          const t   = (max > 1) ? (d.avg - 1) / (max - 1) : 0.5;
          const avgY = padTop + (1 - t) * innerH;
          const hw   = colW * 0.28;
          svg += '<line x1="' + (cx - hw) + '" y1="' + avgY +
                 '" x2="' + (cx + hw) + '" y2="' + avgY +
                 '" stroke="rgba(255,255,255,0.35)" stroke-width="1.5" stroke-linecap="round"/>';
        }
      }
    });

    svg += "</svg>";
    el.innerHTML = svg;

    // week sub-label
    if (data.week_count > 0) {
      subEl.textContent = data.week_count + " check-in" +
        (data.week_count !== 1 ? "s" : "") +
        (data.week_avg !== null && data.week_avg !== undefined
          ? " · avg " + data.week_avg
          : "");
    } else {
      subEl.textContent = "no check-ins yet this week";
    }
  }

  // --- pattern cards ----------------------------------------------------------

  function renderPatterns(data) {
    const card = document.getElementById("patternsCard");
    const list = document.getElementById("patternList");
    const pats = data.patterns || [];

    if (!data.unlocked || pats.length === 0) {
      card.classList.add("hidden");
      return;
    }

    card.classList.remove("hidden");
    list.innerHTML = "";
    pats.forEach(function (p, i) {
      const div = document.createElement("div");
      div.className = "pattern-card";
      div.textContent = p.text;
      list.appendChild(div);
      // Stagger the reveal animation
      setTimeout(function () {
        div.classList.add("visible");
      }, 80 * i);
    });
  }

  // --- stage sub-meter --------------------------------------------------------

  function renderStage(data) {
    const card  = document.getElementById("stageCard");
    const hint  = document.getElementById("stageHint");
    const track = document.getElementById("stageMeterTrack");
    const fill  = document.getElementById("stageFill");

    if (!data.stage_needed) {
      // Fully at Stage 3 — hide the card
      card.classList.add("hidden");
      return;
    }

    card.classList.remove("hidden");
    hint.textContent = data.stage_needed;
    track.classList.remove("hidden");
    fill.style.width = (data.stage_pct || 0) + "%";
  }

  // --- stats row --------------------------------------------------------------

  function renderStats(data) {
    const el = document.getElementById("statsRow");
    const cells = [
      { val: data.count,        label: "total" },
      { val: data.distinct_days, label: "days" },
      {
        val: data.week_avg !== null && data.week_avg !== undefined ? data.week_avg : "—",
        label: "week avg",
      },
    ];
    el.innerHTML = cells.map(function (c) {
      return '<div class="stat-cell">' +
        '<div class="stat-val">' + esc(c.val) + '</div>' +
        '<div class="stat-label">' + esc(c.label) + '</div>' +
        '</div>';
    }).join("");
  }

  // --- public -----------------------------------------------------------------

  window.pulse = {
    refresh: function () { load(); },
  };

  function announceReady() {
    const a = api();
    if (!a) return;
    a.ready();
    load();
  }
  window.addEventListener("pywebviewready", announceReady);
  setTimeout(announceReady, 800);
})();
