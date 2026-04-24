"""Fire-and-forget telemetry transport.

Every call is gated by :func:`is_enabled` and posts asynchronously in a daemon
thread with a 500 ms timeout. All errors are swallowed so telemetry can never
surface as a user-visible failure.
"""

from __future__ import annotations

import threading

import httpx

from grok_install.telemetry.config import is_enabled, load_config
from grok_install.telemetry.events import TelemetryEvent

_TIMEOUT_SECONDS = 0.5


def _post(endpoint: str, payload: dict) -> None:
    try:
        httpx.post(endpoint, json=payload, timeout=_TIMEOUT_SECONDS)
    except Exception:
        return


def emit(event: TelemetryEvent, *, blocking: bool = False) -> bool:
    """Send an event if telemetry is enabled. Returns True if dispatched."""
    if not is_enabled():
        return False
    cfg = load_config()
    if not cfg.endpoint or not cfg.install_id:
        return False
    payload = event.to_payload()
    if blocking:
        _post(cfg.endpoint, payload)
        return True
    thread = threading.Thread(
        target=_post, args=(cfg.endpoint, payload), daemon=True
    )
    thread.start()
    return True


def build_event(name: str, install_id: str, **extra: object) -> TelemetryEvent:
    """Construct a TelemetryEvent with only the allow-listed extra keys."""
    allowed = {"duration_ms", "result"}
    scrubbed = {k: v for k, v in extra.items() if k in allowed}
    return TelemetryEvent(name=name, install_id=install_id, **scrubbed)  # type: ignore[arg-type]
