/* PULSE settings (spec §6): renders itself from the catalogue Python sends, saves each
 * change live, and shows the "?" explainer (what / who / trade-off) for every setting. */
(function () {
  "use strict";

  const groupsEl = document.getElementById("groups");
  const profileSelect = document.getElementById("profileSelect");
  const profileBlurb = document.getElementById("profileBlurb");
  const savedNote = document.getElementById("savedNote");
  let profiles = [];

  function api() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
  }

  function flashSaved() {
    savedNote.textContent = "saved ✓";
    savedNote.style.color = "var(--accent)";
    clearTimeout(flashSaved._t);
    flashSaved._t = setTimeout(function () {
      savedNote.textContent = "changes save automatically";
      savedNote.style.color = "";
    }, 1200);
  }

  async function saveSetting(key, value) {
    const a = api();
    if (a) { await a.set_setting(key, value); flashSaved(); }
  }

  function explainerEl(ex) {
    const box = document.createElement("div");
    box.className = "explainer hidden";
    box.innerHTML =
      '<div class="row"><span class="tag">What:</span> </div>' +
      '<div class="row"><span class="tag who">Who:</span> </div>' +
      '<div class="row"><span class="tag trade">Trade-off:</span> </div>';
    box.children[0].appendChild(document.createTextNode(" " + ex.what));
    box.children[1].appendChild(document.createTextNode(" " + ex.who));
    box.children[2].appendChild(document.createTextNode(" " + ex.tradeoff));
    return box;
  }

  function controlFor(s) {
    const wrap = document.createElement("div");
    wrap.className = "control";
    if (s.kind === "choice") {
      const sel = document.createElement("select");
      s.choices.forEach(function (c) {
        const o = document.createElement("option");
        o.value = c.value; o.textContent = c.label;
        if (c.value === s.value) o.selected = true;
        sel.appendChild(o);
      });
      sel.addEventListener("change", function () { saveSetting(s.key, sel.value); });
      wrap.appendChild(sel);
    } else if (s.kind === "bool") {
      const t = document.createElement("button");
      t.className = "toggle" + (s.value ? " on" : "");
      t.addEventListener("click", function () {
        const on = !t.classList.contains("on");
        t.classList.toggle("on", on);
        saveSetting(s.key, on);
      });
      wrap.appendChild(t);
    } else if (s.kind === "number") {
      const row = document.createElement("div");
      row.className = "num-row";
      const inp = document.createElement("input");
      inp.type = "number"; inp.value = s.value;
      if (s.min != null) inp.min = s.min;
      if (s.max != null) inp.max = s.max;
      inp.step = s.unit === "sec" ? 5 : (s.unit === "/day" ? 1 : 0.5);
      inp.style.minWidth = "88px";
      inp.addEventListener("change", function () {
        let v = parseFloat(inp.value);
        if (isNaN(v)) return;
        if (s.min != null) v = Math.max(s.min, v);
        if (s.max != null) v = Math.min(s.max, v);
        inp.value = v;
        saveSetting(s.key, v);
      });
      row.appendChild(inp);
      if (s.unit) {
        const u = document.createElement("span");
        u.className = "unit"; u.textContent = s.unit;
        row.appendChild(u);
      }
      wrap.appendChild(row);
    }
    return wrap;
  }

  function renderGroups(cat) {
    groupsEl.innerHTML = "";
    cat.groups.forEach(function (g) {
      const gEl = document.createElement("div");
      gEl.className = "group";
      const title = document.createElement("div");
      title.className = "group-title"; title.textContent = g.name;
      gEl.appendChild(title);

      g.settings.forEach(function (s) {
        const card = document.createElement("div");
        card.className = "setting";
        const head = document.createElement("div");
        head.className = "setting-head";

        const label = document.createElement("div");
        label.className = "setting-label";
        const q = document.createElement("span");
        q.className = "qmark"; q.textContent = "?"; q.title = "What this does";
        const name = document.createElement("span");
        name.textContent = s.label;
        label.appendChild(name); label.appendChild(q);

        head.appendChild(label);
        head.appendChild(controlFor(s));
        card.appendChild(head);

        const ex = explainerEl(s.explainer);
        card.appendChild(ex);
        q.addEventListener("click", function () { ex.classList.toggle("hidden"); });

        gEl.appendChild(card);
      });
      groupsEl.appendChild(gEl);
    });
  }

  function renderProfiles(cat) {
    profiles = cat.profiles;
    profileSelect.innerHTML = "";
    profiles.forEach(function (p) {
      const o = document.createElement("option");
      o.value = p.key; o.textContent = p.name;
      if (p.key === cat.active_profile) o.selected = true;
      profileSelect.appendChild(o);
    });
    updateBlurb();
  }
  function updateBlurb() {
    const p = profiles.find(function (x) { return x.key === profileSelect.value; });
    profileBlurb.textContent = p ? p.blurb : "";
  }
  profileSelect.addEventListener("change", updateBlurb);

  document.getElementById("applyProfile").addEventListener("click", async function () {
    const a = api();
    if (!a) return;
    const cat = await a.apply_profile(profileSelect.value);
    renderGroups(cat); renderProfiles(cat); flashSaved();
  });
  document.getElementById("closeBtn").addEventListener("click", function () {
    const a = api();
    if (a) a.close();
  });

  async function init() {
    const a = api();
    if (!a) return;
    const cat = await a.get_catalogue();
    renderProfiles(cat); renderGroups(cat);
  }
  window.addEventListener("pywebviewready", init);
  setTimeout(init, 600);
})();
