"""Machine-level plumbing config loaded from config.yaml (spec §8).

config.yaml is NOT committed (it's in .gitignore) and holds machine-specific values:
DB path override, PocketBase sync URL, and an optional human-readable machine name.
Every user-facing setting lives in SQLite — nothing user-visible goes here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MachineConfig:
    db_path: str | None = None       # overrides the default %LOCALAPPDATA%/PULSE/pulse.db
    sync_url: str | None = None      # PocketBase base URL; Tailnet only, never internet-exposed
    machine_name: str | None = None  # optional friendly name shown in multi-machine views

    @classmethod
    def load(cls, path: str | Path | None = None) -> "MachineConfig":
        """Load from config.yaml; return defaults silently if the file is missing."""
        p = Path(path) if path else _default_config_path()
        if not p.exists():
            return cls()
        try:
            import yaml  # PyYAML — already in requirements.txt
            with p.open(encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            return cls()
        return cls(
            db_path=data.get("db_path") or None,
            sync_url=data.get("sync_url") or None,
            machine_name=data.get("machine_name") or None,
        )


def _default_config_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "PULSE" / "config.yaml"
