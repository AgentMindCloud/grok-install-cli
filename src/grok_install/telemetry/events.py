"""Telemetry event schema.

Every field that could ever be emitted lives on :class:`TelemetryEvent`.
There is intentionally no place for paths, agent names, config contents,
hostnames, or anything that could identify a user or project.
"""

from __future__ import annotations

import json
import platform as _platform
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from grok_install import __version__ as _cli_version

EventName = Literal[
    "cli.invoke",
    "scan.run",
    "install.start",
    "install.success",
    "install.failure",
    "run.start",
    "run.end",
]

_ALLOWED_KEYS = frozenset(
    {
        "name",
        "cli_version",
        "python_version",
        "platform",
        "install_id",
        "duration_ms",
        "result",
        "emitted_at",
    }
)


@dataclass(frozen=True)
class TelemetryEvent:
    """A single telemetry payload. All fields are non-identifying."""

    name: EventName
    install_id: str
    cli_version: str = field(default_factory=lambda: _cli_version)
    python_version: str = field(default_factory=lambda: _platform.python_version())
    platform: str = field(default_factory=lambda: sys.platform)
    duration_ms: int | None = None
    result: Literal["ok", "fail"] | None = None
    emitted_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_payload(self) -> dict[str, Any]:
        """Serialise to a dict with only allow-listed keys."""
        raw = asdict(self)
        return {k: v for k, v in raw.items() if k in _ALLOWED_KEYS and v is not None}

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True)


def schema_description() -> str:
    """Human-readable description of what an event contains — used by `telemetry status`."""
    return json.dumps(
        {
            "name": "one of: cli.invoke, scan.run, install.start, install.success, "
            "install.failure, run.start, run.end",
            "install_id": "anonymous UUIDv4 generated on opt-in; deleted on opt-out",
            "cli_version": "grok-install version string",
            "python_version": "Python interpreter version",
            "platform": "sys.platform (e.g. 'linux', 'darwin', 'win32')",
            "duration_ms": "integer milliseconds for timed events (optional)",
            "result": "'ok' or 'fail' for outcome events (optional)",
            "emitted_at": "ISO-8601 UTC timestamp",
        },
        indent=2,
    )
