"""User settings, preference profiles, and the "?" explainers (spec §6).

Nothing is hardcoded to one person's preference (§6): every enforcement style ships as
a setting, each with a plain-language explainer (what it does · who it tends to suit ·
the trade-off). Profiles are *tunable starting points, NOT diagnoses* (§2) — presets
that set sensible defaults you then freely edit.

All values live in SQLite (§8); this module owns the JSON encoding and the defaults.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .config import TimingConfig
from .storage import PulseStorage

_FIRST_RUN_KEY = "first_run_complete"
_PROFILE_KEY = "active_profile"


@dataclass(frozen=True)
class Explainer:
    """The three things every setting must explain, in non-clinical language (§6).
    'who' is framed as "tends to suit people who…", never "pick this if you have X"."""

    what: str
    who: str
    tradeoff: str


@dataclass(frozen=True)
class Choice:
    value: str
    label: str


@dataclass(frozen=True)
class SettingDef:
    key: str
    label: str
    kind: str  # "choice" | "number" | "bool"
    default: object
    explainer: Explainer
    group: str = "General"
    choices: tuple[Choice, ...] = ()
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None


# --- the settings catalogue (§6) ----------------------------------------------

SETTING_DEFS: tuple[SettingDef, ...] = (
    SettingDef(
        key="enforcement_light",
        label="Light break style",
        kind="choice",
        default="corner_countdown",
        group="Light breaks",
        choices=(
            Choice("corner_countdown", "Corner countdown (gentle)"),
            Choice("soft_overlay", "Soft full-screen (dismissible)"),
            Choice("hard_lock", "Hard-lock (a wall until done)"),
        ),
        explainer=Explainer(
            what="How a light movement break asks for your attention — a quiet corner "
            "countdown, a dismissible full-screen card, or a persistent wall.",
            who="The corner countdown tends to suit people who lose the thread when "
            "yanked out of focus; the overlay suits people who scroll past quiet nudges.",
            tradeoff="Gentler styles are easy to ignore on a rough day; firmer styles "
            "protect the habit but can cost you your train of thought.",
        ),
    ),
    SettingDef(
        key="enforcement_training",
        label="Training break style",
        kind="choice",
        default="session_card",
        group="Training breaks",
        choices=(
            Choice("session_card", "Full-screen session card"),
            Choice("soft_overlay", "Soft overlay (dismissible)"),
            Choice("hard_lock", "Hard-lock (a wall until done)"),
        ),
        explainer=Explainer(
            what="How a harder training break holds you to it. Hard-lock puts up a "
            "full-screen wall until the session timer completes.",
            who="Tends to help people who override softer prompts and want a wall they "
            "can't argue with.",
            tradeoff="Honest note: it's software, not handcuffs — a determined person "
            "can get past it, and that's okay; it works because you chose it, not because "
            "it's unbreakable. If being force-stopped costs you the thread, use a gentler "
            "style instead.",
        ),
    ),
    SettingDef(
        key="snooze_light",
        label="Snooze",
        kind="choice",
        default="off",
        group="Light breaks",
        choices=(
            Choice("off", "Off"),
            Choice("one", "One snooze"),
            Choice("multi", "Multiple snoozes"),
        ),
        explainer=Explainer(
            what="Whether a break can be pushed back, and how many times.",
            who="Off tends to suit people who, given one snooze, will snooze forever; "
            "a snooze or two suits people who just need to finish the current thing.",
            tradeoff="More snoozes mean more control, but also more ways to quietly opt "
            "out of the habit entirely.",
        ),
    ),
    SettingDef(
        key="timing_mode",
        label="Timing",
        kind="choice",
        default="dynamic",
        group="Light breaks",
        choices=(
            Choice("dynamic", "Dynamic — you start the break"),
            Choice("fixed", "Fixed — on the app's clock"),
        ),
        explainer=Explainer(
            what="Whether you trigger the break yourself at a natural stopping point, or "
            "it lands on a fixed schedule.",
            who="Dynamic tends to suit people who hate being interrupted mid-sentence; "
            "fixed suits people who want a predictable, unchanging rhythm.",
            tradeoff="Dynamic relies on you to actually take it; fixed is predictable but "
            "can land mid-thought.",
        ),
    ),
    SettingDef(
        key="warning_lead_minutes",
        label="Advance warning",
        kind="number",
        default=5.0,
        group="Light breaks",
        unit="min",
        minimum=0.5,
        maximum=15.0,
        explainer=Explainer(
            what="How long before a break the corner countdown appears, so you can line "
            "it up with a natural stopping point.",
            who="More warning tends to suit people who need to see a transition coming to "
            "make it bearable.",
            tradeoff="More warning means smoother transitions but a countdown in your eye "
            "for longer.",
        ),
    ),
    SettingDef(
        key="light_interval_minutes",
        label="Break interval",
        kind="number",
        default=30.0,
        group="Light breaks",
        unit="min",
        minimum=10.0,
        maximum=90.0,
        explainer=Explainer(
            what="How much active work time builds up between light movement breaks.",
            who="Shorter suits people who stiffen up or fade fast; longer suits people who "
            "need long unbroken stretches for deep work.",
            tradeoff="Shorter means more movement but more interruptions; longer means "
            "deeper focus but more sitting.",
        ),
    ),
    SettingDef(
        key="light_break_seconds",
        label="Break length",
        kind="number",
        default=90.0,
        group="Light breaks",
        unit="sec",
        minimum=30.0,
        maximum=300.0,
        explainer=Explainer(
            what="How long the self-started movement timer runs.",
            who="Shorter suits people who just need to stand and reset; longer suits people "
            "who want a proper walk.",
            tradeoff="Longer breaks move you more but pull you away from work for longer.",
        ),
    ),
    SettingDef(
        key="max_training_sessions_per_day",
        label="Daily training cap",
        kind="number",
        default=2.0,
        group="Training breaks",
        unit="/day",
        minimum=0.0,
        maximum=4.0,
        explainer=Explainer(
            what="The most hard training sessions offered in a day (the Big Break counts "
            "as one).",
            who="A low cap suits almost everyone — the evidence goal is frequent light "
            "movement plus one or two hard efforts, not piled-up hard volume.",
            tradeoff="A higher cap allows more training but risks overtraining, which can "
            "even blunt mental performance.",
        ),
    ),
    SettingDef(
        key="training_enabled",
        label="Training layer",
        kind="bool",
        default=True,
        group="Training breaks",
        explainer=Explainer(
            what="Whether the occasional harder training break is offered at all.",
            who="Turning it off suits people who only want gentle movement nudges and "
            "handle their own workouts.",
            tradeoff="Off means no strength/conditioning prompts — purely the light layer.",
        ),
    ),
    SettingDef(
        key="tracking_enabled",
        label="Reflection & ratings",
        kind="bool",
        default=True,
        group="Reflection",
        explainer=Explainer(
            what="Whether PULSE asks how blocks went and builds the graph and insights.",
            who="On suits people who want the mirror — to see what actually helps them; "
            "off suits people who just want movement nudges and nothing logged.",
            tradeoff="Off means no graph, no unlock meter, no patterns — just the breaks.",
        ),
    ),
    SettingDef(
        key="meal_windows_enabled",
        label="Meal windows",
        kind="bool",
        default=True,
        group="Body floor",
        explainer=Explainer(
            what="Whether the first break inside a meal window asks 'have you eaten "
            "today?' and offers a longer 'go make a sandwich' break.",
            who="Tends to help people who skip food in hyperfocus until the crash.",
            tradeoff="Off removes the food prompt (hydration still rides on every break).",
        ),
    ),
    SettingDef(
        key="rating_scale_style",
        label="Rating scale",
        kind="choice",
        default="numbers",
        group="Reflection",
        choices=(
            Choice("numbers", "Numbers (1–10)"),
            Choice("faces", "Faces"),
            Choice("words", "Labelled words"),
        ),
        explainer=Explainer(
            what="How you rate a block — a 1–10 number, a row of faces, or words.",
            who="Numbers suit people who think in fine gradations; faces or words suit "
            "people for whom a number stops meaning anything.",
            tradeoff="Numbers are the most granular; faces and words are faster but "
            "coarser.",
        ),
    ),
    # --- Appearance (§2 / §8) — sensory and readability preferences ----------
    SettingDef(
        key="appearance_theme",
        label="Colour theme",
        kind="choice",
        default="dark",
        group="Appearance",
        choices=(
            Choice("dark",     "Dark (default)"),
            Choice("light",    "Light"),
            Choice("dark_hc",  "Dark — high contrast"),
            Choice("light_hc", "Light — high contrast"),
        ),
        explainer=Explainer(
            what="The overall background and text palette. High-contrast options push "
            "foreground text further from the background for people who need stronger "
            "separation.",
            who="Light suits people who work near a bright window; high contrast suits "
            "people with strong light sensitivity or who find low-contrast text physically "
            "tiring.",
            tradeoff="High contrast can feel visually harsh after a long session if your "
            "sensitivity runs the other way — you can always flip back.",
        ),
    ),
    SettingDef(
        key="appearance_accent",
        label="Accent colour",
        kind="choice",
        default="teal",
        group="Appearance",
        choices=(
            Choice("teal",     "Teal (default)"),
            Choice("violet",   "Violet"),
            Choice("coral",    "Coral"),
            Choice("sky",      "Sky blue"),
            Choice("sage",     "Sage green"),
            Choice("peach",    "Peach"),
            Choice("lavender", "Lavender"),
        ),
        explainer=Explainer(
            what="The highlight colour used for timers, buttons, and the graph. "
            "All options are tested for readable contrast on both dark and light themes.",
            who="Colour preference is personal and sensory — pick whatever feels "
            "calm and easy to look at for you.",
            tradeoff="No real trade-off here. Change it any time.",
        ),
    ),
    SettingDef(
        key="appearance_font_size",
        label="Text size",
        kind="choice",
        default="normal",
        group="Appearance",
        choices=(
            Choice("small",  "Small (88%)"),
            Choice("normal", "Normal (default)"),
            Choice("large",  "Large (115%)"),
            Choice("xlarge", "Extra large (135%)"),
        ),
        explainer=Explainer(
            what="Scales all text and spacing up or down uniformly across every "
            "PULSE window. Uses the browser zoom mechanism so layout proportions "
            "stay consistent.",
            who="Larger sizes tend to suit people who find small text tiring or "
            "need more reading room; smaller suits people who want more content "
            "on screen.",
            tradeoff="At Extra large, fixed-size cards may clip a word at the "
            "edge — the content is still there, just scroll or resize the window.",
        ),
    ),
    SettingDef(
        key="appearance_font",
        label="Font style",
        kind="choice",
        default="default",
        group="Appearance",
        choices=(
            Choice("default", "Default (Segoe UI / system sans-serif)"),
            Choice("mono",    "Monospace (Consolas)"),
            Choice("serif",   "Serif (Georgia)"),
        ),
        explainer=Explainer(
            what="The typeface used throughout PULSE. All options are system fonts "
            "guaranteed to be present on Windows — no downloads.",
            who="Monospace tends to suit people who find regular sans-serif fonts "
            "visually busy; serif suits people who read prose more comfortably with "
            "letter serifs as anchors.",
            tradeoff="Monospace uses more horizontal space — some labels may wrap "
            "at smaller window sizes.",
        ),
    ),
    # --- System --------------------------------------------------------------
    SettingDef(
        key="start_with_windows",
        label="Start with Windows",
        kind="bool",
        default=False,
        group="System",
        explainer=Explainer(
            what="Adds PULSE to the per-user Windows startup list (HKCU Run key) "
            "so it launches automatically when you log in. No administrator "
            "permission is required — it only applies to your account.",
            who="Anyone who wants PULSE running in the background from the moment "
            "they sit down, without remembering to launch it manually.",
            tradeoff="Only takes effect in the packaged app (not during development). "
            "Turn it off here to remove the startup entry — PULSE won't launch "
            "on its own until you turn it back on.",
        ),
    ),
    # --- Sync (§12) ----------------------------------------------------------
    SettingDef(
        key="sync_enabled",
        label="PocketBase sync",
        kind="bool",
        default=False,
        group="Sync",
        explainer=Explainer(
            what="Syncs your checkin and break history to a self-hosted PocketBase "
            "instance over your Tailscale private network. Requires a sync_url in "
            "config.yaml and a PULSE_PB_TOKEN environment variable — the token is "
            "never stored in the app or any file.",
            who="Anyone running PULSE on more than one machine, or who wants a "
            "second copy of their data beyond the local SQLite file. Completely "
            "optional — PULSE works fully offline without it.",
            tradeoff="Off by default because most users don't run PocketBase. "
            "Enabling without a valid URL and token does nothing — no data leaves "
            "the machine unless both are configured.",
        ),
    ),
    # --- Focus Guard ---------------------------------------------------------
    SettingDef(
        key="focus_mode_enabled",
        label="Focus Guard",
        kind="bool",
        default=False,
        group="Focus Guard",
        explainer=Explainer(
            what="While on, the light layer shows a quiet corner countdown but never "
            "escalates or pulses — you can wave it off or simply ignore it. "
            "Training breaks wait until your focus block ends naturally.",
            who="Tends to suit people who need 90+ minutes of unbroken concentration "
            "and find mid-task interruptions very expensive to recover from.",
            tradeoff="The light layer becomes advisory only, which makes it easier to "
            "ignore entirely. Hydration and meal windows still fire on any break that "
            "does land; the boundary break still arrives at the block's edge — the body "
            "floor doesn't move.",
        ),
    ),
)

SETTING_BY_KEY: dict[str, SettingDef] = {d.key: d for d in SETTING_DEFS}


# --- preference profiles (tunable starting points, NOT diagnoses — §6) ---------

@dataclass(frozen=True)
class Profile:
    key: str
    name: str
    blurb: str
    overrides: dict[str, object]


PROFILES: tuple[Profile, ...] = (
    Profile(
        "long_ramp",
        "Long ramp / protect focus",
        "Longer stretches, corner countdown only, training saved for natural edges — "
        "for deep work that needs a runway.",
        {
            "light_interval_minutes": 45.0,
            "warning_lead_minutes": 5.0,
            "enforcement_light": "corner_countdown",
            "snooze_light": "off",
            "timing_mode": "dynamic",
        },
    ),
    Profile(
        "frequent_gentle",
        "Frequent gentle nudges",
        "Shorter stretches, soft reminders, low friction — for staying loose and moving "
        "often.",
        {
            "light_interval_minutes": 20.0,
            "warning_lead_minutes": 3.0,
            "enforcement_light": "soft_overlay",
            "snooze_light": "one",
        },
    ),
    Profile(
        "high_predictability",
        "High predictability",
        "Maximum advance warning, fixed timing, no surprises — a consistent daily rhythm.",
        {
            "timing_mode": "fixed",
            "warning_lead_minutes": 10.0,
            "light_interval_minutes": 30.0,
            "enforcement_light": "corner_countdown",
        },
    ),
    Profile(
        "firm_accountability",
        "Firm accountability",
        "Hard-lock on, snooze off, stricter completion — for when softer prompts get "
        "overridden.",
        {
            "enforcement_light": "hard_lock",
            "enforcement_training": "hard_lock",
            "snooze_light": "off",
            "warning_lead_minutes": 5.0,
        },
    ),
    Profile(
        "minimal_movement",
        "Minimal / just movement",
        "Light movement only — no training layer, no tracking. Just get up and move.",
        {
            "training_enabled": False,
            "tracking_enabled": False,
            "enforcement_light": "corner_countdown",
        },
    ),
)

PROFILE_BY_KEY: dict[str, Profile] = {p.key: p for p in PROFILES}


def catalogue_payload(settings: "Settings") -> dict:
    """A JSON-able description of every setting (grouped), its current value, choices,
    and explainer — so the settings UI renders itself from data (§6: every setting has
    a '?' bubble). Also carries the profiles for the profile picker."""
    groups: dict[str, list] = {}
    for d in SETTING_DEFS:
        groups.setdefault(d.group, []).append(
            {
                "key": d.key,
                "label": d.label,
                "kind": d.kind,
                "value": settings.get(d.key),
                "unit": d.unit,
                "min": d.minimum,
                "max": d.maximum,
                "choices": [{"value": c.value, "label": c.label} for c in d.choices],
                "explainer": {
                    "what": d.explainer.what,
                    "who": d.explainer.who,
                    "tradeoff": d.explainer.tradeoff,
                },
            }
        )
    return {
        "groups": [{"name": name, "settings": items} for name, items in groups.items()],
        "profiles": profiles_payload(),
        "active_profile": settings.active_profile,
    }


def profiles_payload() -> list[dict]:
    return [
        {"key": p.key, "name": p.name, "blurb": p.blurb} for p in PROFILES
    ]


class Settings:
    """Effective settings = stored overrides on top of the catalogue defaults."""

    def __init__(self, storage: PulseStorage) -> None:
        self._storage = storage

    # --- get / set -------------------------------------------------------------

    def get(self, key: str):
        raw = self._storage.get_setting(key)
        if raw is not None:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        return SETTING_BY_KEY[key].default

    def set(self, key: str, value) -> None:
        self._validate(key, value)
        self._storage.set_setting(key, json.dumps(value))

    def all(self) -> dict[str, object]:
        return {d.key: self.get(d.key) for d in SETTING_DEFS}

    def _validate(self, key: str, value) -> None:
        d = SETTING_BY_KEY.get(key)
        if d is None:
            raise KeyError(f"unknown setting {key!r}")
        if d.kind == "choice":
            valid = {c.value for c in d.choices}
            if value not in valid:
                raise ValueError(f"{key}: {value!r} not in {sorted(valid)}")
        elif d.kind == "number":
            if not isinstance(value, (int, float)):
                raise ValueError(f"{key}: expected a number")
            if d.minimum is not None and value < d.minimum:
                raise ValueError(f"{key}: below minimum {d.minimum}")
            if d.maximum is not None and value > d.maximum:
                raise ValueError(f"{key}: above maximum {d.maximum}")
        elif d.kind == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"{key}: expected a bool")

    # --- profiles --------------------------------------------------------------

    def apply_profile(self, profile_key: str) -> None:
        profile = PROFILE_BY_KEY[profile_key]
        for key, value in profile.overrides.items():
            self.set(key, value)
        self._storage.set_setting(_PROFILE_KEY, json.dumps(profile_key))

    @property
    def active_profile(self) -> str | None:
        raw = self._storage.get_setting(_PROFILE_KEY)
        return json.loads(raw) if raw is not None else None

    # --- first run -------------------------------------------------------------

    @property
    def first_run_complete(self) -> bool:
        raw = self._storage.get_setting(_FIRST_RUN_KEY)
        return bool(json.loads(raw)) if raw is not None else False

    def mark_first_run_complete(self) -> None:
        self._storage.set_setting(_FIRST_RUN_KEY, json.dumps(True))

    # --- derive the engine config ---------------------------------------------

    def scale_max(self) -> int:
        return {"numbers": 10, "faces": 5, "words": 5}.get(
            self.get("rating_scale_style"), 10
        )

    def to_timing_config(self) -> TimingConfig:
        interval = float(self.get("light_interval_minutes"))
        lead = float(self.get("warning_lead_minutes"))
        # TimingConfig requires the warning to fit inside the interval; clamp defensively
        # so a hand-edited combination can never crash the engine.
        if lead >= interval:
            lead = max(0.5, interval / 2.0)
        return TimingConfig(
            light_interval_minutes=interval,
            warning_lead_minutes=lead,
            light_break_seconds=float(self.get("light_break_seconds")),
            max_training_sessions_per_day=int(self.get("max_training_sessions_per_day")),
        )
