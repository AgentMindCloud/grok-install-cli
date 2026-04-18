"""Persistent opt-in state for telemetry.

Stored at ``~/.grokinstall/config.json`` (override via ``GROKINSTALL_CONFIG_DIR``).
Opt-in is explicit, kill-switchable by env var, and deletes the install id on opt-out.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENV_KILL_SWITCH = "GROKINSTALL_TELEMETRY"
ENV_CONFIG_DIR = "GROKINSTALL_CONFIG_DIR"
_CONFIG_FILENAME = "config.json"


@dataclass
class TelemetryConfig:
    enabled: bool = False
    install_id: str | None = None
    endpoint: str | None = None
    opted_in_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def config_dir() -> Path:
    override = os.environ.get(ENV_CONFIG_DIR)
    if override:
        return Path(override)
    return Path.home() / ".grokinstall"


def config_path() -> Path:
    return config_dir() / _CONFIG_FILENAME


def _kill_switched() -> bool:
    raw = os.environ.get(ENV_KILL_SWITCH)
    if raw is None:
        return False
    return raw.strip().lower() in {"0", "false", "no", "off"}


def load_config() -> TelemetryConfig:
    """Load the telemetry config from disk. Returns the default if no file exists."""
    path = config_path()
    if not path.is_file():
        return TelemetryConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return TelemetryConfig()
    section = raw.get("telemetry") if isinstance(raw, dict) else None
    if not isinstance(section, dict):
        return TelemetryConfig()
    return TelemetryConfig(
        enabled=bool(section.get("enabled", False)),
        install_id=section.get("install_id"),
        endpoint=section.get("endpoint"),
        opted_in_at=section.get("opted_in_at"),
    )


def save_config(cfg: TelemetryConfig) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8")) or {}
            if not isinstance(existing, dict):
                existing = {}
        except (OSError, json.JSONDecodeError):
            existing = {}
    existing["telemetry"] = cfg.to_dict()
    path.write_text(json.dumps(existing, indent=2, sort_keys=True), encoding="utf-8")


def enable_telemetry(endpoint: str | None = None) -> TelemetryConfig:
    """Turn telemetry on. Generates a fresh install_id on first opt-in."""
    current = load_config()
    cfg = TelemetryConfig(
        enabled=True,
        install_id=current.install_id or str(uuid.uuid4()),
        endpoint=endpoint if endpoint is not None else current.endpoint,
        opted_in_at=datetime.now(timezone.utc).isoformat(),
    )
    save_config(cfg)
    return cfg


def disable_telemetry() -> TelemetryConfig:
    """Turn telemetry off and wipe the install_id."""
    cfg = TelemetryConfig(enabled=False, install_id=None, endpoint=None, opted_in_at=None)
    save_config(cfg)
    return cfg


def is_enabled() -> bool:
    """Honor the env kill switch first, then the persisted config."""
    if _kill_switched():
        return False
    cfg = load_config()
    return bool(cfg.enabled and cfg.install_id and cfg.endpoint)
