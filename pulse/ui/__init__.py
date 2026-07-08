"""PULSE UI layer (pywebview). All surfaces — corner widget, break card, check-in,
graphs, settings — are HTML/CSS/JS rendered by pywebview (spec §3)."""

from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent / "web"
