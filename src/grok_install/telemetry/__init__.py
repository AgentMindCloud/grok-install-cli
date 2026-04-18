"""Opt-in telemetry for grok-install.

Telemetry is OFF by default and every event respects:
  1. `GROKINSTALL_TELEMETRY=0` env kill switch (forces OFF)
  2. Persistent opt-in config at `~/.grokinstall/config.json`
  3. A never-raise, 500 ms timeout POST transport

Events carry no PII: no paths, no agent names, no config contents.
See :func:`grok_install.telemetry.events.schema_description` for the exact schema.
"""

from grok_install.telemetry.client import build_event, emit
from grok_install.telemetry.config import (
    ENV_CONFIG_DIR,
    ENV_KILL_SWITCH,
    TelemetryConfig,
    config_path,
    disable_telemetry,
    enable_telemetry,
    is_enabled,
    load_config,
)
from grok_install.telemetry.events import EventName, TelemetryEvent, schema_description

__all__ = [
    "ENV_CONFIG_DIR",
    "ENV_KILL_SWITCH",
    "EventName",
    "TelemetryConfig",
    "TelemetryEvent",
    "build_event",
    "config_path",
    "disable_telemetry",
    "emit",
    "enable_telemetry",
    "is_enabled",
    "load_config",
    "schema_description",
]
