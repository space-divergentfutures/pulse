/* PULSE guided first-run (spec §6): opening copy -> pick a starting point -> begin.
 * The profile is a tunable starting point, never a diagnosis. */
(function () {
  "use strict";

  const introScreen = document.getElementById("introScreen");
  const profileScreen = document.getElementById("profileScreen");
  const profilesEl = document.getElementById("profiles");
  const startBtn = document.getElementById("startBtn");
  let selected = null;

  function api() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
  }

  function show(screen) {
    introScreen.classList.toggle("hidden", screen !== "intro");
    profileScreen.classList.toggle("hidden", screen !== "profiles");
  }

  function renderProfiles(profiles) {
    profilesEl.innerHTML = "";
    profiles.forEach(function (p) {
      const card = document.createElement("button");
      card.className = "profile";
      card.innerHTML =
        '<div class="p-name"></div><div class="p-blurb"></div>';
      card.querySelector(".p-name").textContent = p.name;
      card.querySelector(".p-blurb").textContent = p.blurb;
      card.addEventListener("click", function () {
        selected = p.key;
        Array.prototype.forEach.call(
          profilesEl.children, function (c) { c.classList.remove("selected"); });
        card.classList.add("selected");
        startBtn.disabled = false;
      });
      profilesEl.appendChild(card);
    });
  }

  document.getElementById("toProfiles").addEventListener("click", function () {
    show("profiles");
  });
  document.getElementById("backToIntro").addEventListener("click", function () {
    show("intro");
  });
  startBtn.addEventListener("click", function () {
    const a = api();
    if (a && selected) a.finish(selected);
  });
  document.getElementById("skipBtn").addEventListener("click", function () {
    const a = api();
    if (a) a.finish(null); // null => keep the gentle defaults
  });

  async function init() {
    const a = api();
    if (!a) return;
    const profiles = await a.get_profiles();
    renderProfiles(profiles);
  }
  window.addEventListener("pywebviewready", init);
  setTimeout(init, 600);
})();
