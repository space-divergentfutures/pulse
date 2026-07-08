"""Appearance theme system (spec §2, §8).

Curated presets rather than a raw colour picker: tested accents, palettes
covering dark/light/high-contrast needs, and font options that matter most
for sensory-sensitive and neurodivergent users.

Usage:
    vars = build_vars(settings)      # dict of CSS custom-property → value
    inject_theme(pywebview_window, vars)   # injects a :root override block
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Accent colour presets
# Each supplies --accent (label / count text), --accent-btn (button rest),
# --accent-btn-hi (button hover), and --done (completion positive).
# ---------------------------------------------------------------------------

ACCENT_PRESETS: dict[str, dict[str, str]] = {
    "teal": {
        "--accent":        "#7fd1c1",
        "--accent-btn":    "#2f6f63",
        "--accent-btn-hi": "#3a8577",
        "--done":          "#7fd1a0",
    },
    "violet": {
        "--accent":        "#a78bfa",
        "--accent-btn":    "#4c2d9e",
        "--accent-btn-hi": "#5c3ab0",
        "--done":          "#a3e4a3",
    },
    "coral": {
        "--accent":        "#f08080",
        "--accent-btn":    "#883030",
        "--accent-btn-hi": "#9e3c3c",
        "--done":          "#90d490",
    },
    "sky": {
        "--accent":        "#7ec8e3",
        "--accent-btn":    "#27637a",
        "--accent-btn-hi": "#307890",
        "--done":          "#7fd1a0",
    },
    "sage": {
        "--accent":        "#90c490",
        "--accent-btn":    "#38663a",
        "--accent-btn-hi": "#447548",
        "--done":          "#90c490",
    },
    "peach": {
        "--accent":        "#f4a460",
        "--accent-btn":    "#7a4a22",
        "--accent-btn-hi": "#8f5a2a",
        "--done":          "#90c490",
    },
    "lavender": {
        "--accent":        "#c8a0d4",
        "--accent-btn":    "#6b3a7e",
        "--accent-btn-hi": "#7c4590",
        "--done":          "#90c490",
    },
}

# ---------------------------------------------------------------------------
# Background + text palettes
# Sets all colour vars used across widget.css, break_card.css, checkin.css,
# training_card.css, and onboard.css in one block.
# ---------------------------------------------------------------------------

THEME_PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "--bg":      "#12141a",
        "--card-a":  "#1b1f2a",
        "--card-b":  "#12141a",
        "--ink":     "#e8ebf2",
        "--muted":   "#8b93a7",
        "--warn":    "#f2b84b",
        "--water":   "#6db3d6",
        "--chip":    "#232838",
        "--grid":    "rgba(255,255,255,0.10)",
        "--panel":   "#171a23",
        "--panel-2": "#1e2230",
        "--line":    "rgba(255,255,255,0.08)",
        "--sel":     "rgba(127,209,193,0.16)",
        "--faint":   "#6b7386",
    },
    "light": {
        "--bg":      "#f0f2f7",
        "--card-a":  "#ffffff",
        "--card-b":  "#f0f2f7",
        "--ink":     "#1a1d26",
        "--muted":   "#5c6475",
        "--warn":    "#c2770a",
        "--water":   "#2670a0",
        "--chip":    "#dde2ec",
        "--grid":    "rgba(0,0,0,0.12)",
        "--panel":   "#f8f9fc",
        "--panel-2": "#eef0f5",
        "--line":    "rgba(0,0,0,0.09)",
        "--sel":     "rgba(47,111,99,0.12)",
        "--faint":   "#8a93a6",
    },
    "dark_hc": {
        "--bg":      "#000000",
        "--card-a":  "#0d0d0d",
        "--card-b":  "#000000",
        "--ink":     "#ffffff",
        "--muted":   "#cccccc",
        "--warn":    "#ffd700",
        "--water":   "#66ccff",
        "--chip":    "#1a1a1a",
        "--grid":    "rgba(255,255,255,0.20)",
        "--panel":   "#111111",
        "--panel-2": "#1a1a1a",
        "--line":    "rgba(255,255,255,0.20)",
        "--sel":     "rgba(255,255,255,0.15)",
        "--faint":   "#aaaaaa",
    },
    "light_hc": {
        "--bg":      "#ffffff",
        "--card-a":  "#ffffff",
        "--card-b":  "#f8f8f8",
        "--ink":     "#000000",
        "--muted":   "#222222",
        "--warn":    "#8a4500",
        "--water":   "#004080",
        "--chip":    "#dddddd",
        "--grid":    "rgba(0,0,0,0.25)",
        "--panel":   "#f8f8f8",
        "--panel-2": "#eeeeee",
        "--line":    "rgba(0,0,0,0.20)",
        "--sel":     "rgba(0,0,0,0.08)",
        "--faint":   "#444444",
    },
}

FONT_FAMILIES: dict[str, str] = {
    "default": '"Segoe UI", system-ui, sans-serif',
    "mono":    '"Consolas", "Courier New", monospace',
    "serif":   '"Georgia", "Times New Roman", serif',
}

# Browser zoom level — scales fonts, spacing, and all layout uniformly.
FONT_SIZE_ZOOM: dict[str, float] = {
    "small":  0.88,
    "normal": 1.0,
    "large":  1.15,
    "xlarge": 1.35,
}


def build_vars(settings) -> dict[str, str]:
    """Return the full set of CSS custom-property overrides for the current settings."""
    vars: dict[str, str] = {}
    vars.update(THEME_PALETTES.get(settings.get("appearance_theme"), THEME_PALETTES["dark"]))
    vars.update(ACCENT_PRESETS.get(settings.get("appearance_accent"), ACCENT_PRESETS["teal"]))
    vars["--font-family"] = FONT_FAMILIES.get(
        settings.get("appearance_font"), FONT_FAMILIES["default"]
    )
    vars["--ui-zoom"] = str(FONT_SIZE_ZOOM.get(settings.get("appearance_font_size"), 1.0))
    return vars


def inject_theme(window, vars: dict[str, str]) -> None:
    """Inject a :root CSS override block into a live pywebview window.

    Creates (or replaces) a <style id="_pt"> element in <head> so the call
    is idempotent — repeated calls update rather than accumulate."""
    css_lines = [":root {"]
    for k, v in vars.items():
        css_lines.append(f"  {k}: {v};")
    css_lines.append("}")
    # Escape for a JS template-literal string (only backticks are special here)
    css = "\n".join(css_lines).replace("\\", "\\\\").replace("`", "\\`")
    js = (
        "(function(){"
        "var e=document.getElementById('_pt');"
        "if(!e){e=document.createElement('style');e.id='_pt';document.head.appendChild(e);}"
        f"e.textContent=`{css}`;"
        "})()"
    )
    window.evaluate_js(js)
