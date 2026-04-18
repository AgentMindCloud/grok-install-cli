"""Tests for the opt-in telemetry module.

These tests verify the three invariants we care about most:
  1. Default state is OFF — no network traffic happens without explicit opt-in.
  2. The ``GROKINSTALL_TELEMETRY=0`` env kill switch overrides a persisted enable.
  3. The event payload only contains allow-listed, non-identifying keys.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from grok_install import telemetry
from grok_install.telemetry.client import emit
from grok_install.telemetry.config import (
    ENV_CONFIG_DIR,
    ENV_KILL_SWITCH,
    disable_telemetry,
    enable_telemetry,
    is_enabled,
    load_config,
)
from grok_install.telemetry.events import TelemetryEvent, schema_description


@pytest.fixture
def tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(ENV_CONFIG_DIR, str(tmp_path))
    monkeypatch.delenv(ENV_KILL_SWITCH, raising=False)
    return tmp_path


def test_default_is_disabled(tmp_home: Path) -> None:
    cfg = load_config()
    assert cfg.enabled is False
    assert cfg.install_id is None
    assert is_enabled() is False


def test_enable_generates_install_id_and_persists(tmp_home: Path) -> None:
    cfg = enable_telemetry(endpoint="https://example.invalid/events")
    assert cfg.enabled is True
    assert cfg.install_id
    assert cfg.endpoint == "https://example.invalid/events"
    # Second load from disk should see the persisted state.
    loaded = load_config()
    assert loaded.enabled is True
    assert loaded.install_id == cfg.install_id
    assert is_enabled() is True


def test_enable_is_idempotent_install_id_stable(tmp_home: Path) -> None:
    first = enable_telemetry(endpoint="https://example.invalid/events")
    second = enable_telemetry(endpoint="https://example.invalid/events")
    assert first.install_id == second.install_id


def test_disable_wipes_install_id(tmp_home: Path) -> None:
    enable_telemetry(endpoint="https://example.invalid/events")
    disable_telemetry()
    cfg = load_config()
    assert cfg.enabled is False
    assert cfg.install_id is None
    assert cfg.endpoint is None
    assert is_enabled() is False


def test_kill_switch_overrides_enabled(
    tmp_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_telemetry(endpoint="https://example.invalid/events")
    assert is_enabled() is True
    monkeypatch.setenv(ENV_KILL_SWITCH, "0")
    assert is_enabled() is False


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "No", "off"])
def test_kill_switch_honours_common_values(
    tmp_home: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    enable_telemetry(endpoint="https://example.invalid/events")
    monkeypatch.setenv(ENV_KILL_SWITCH, value)
    assert is_enabled() is False


def test_corrupt_config_returns_default(tmp_home: Path) -> None:
    (tmp_home / "config.json").write_text("{not json", encoding="utf-8")
    cfg = load_config()
    assert cfg.enabled is False


def test_save_preserves_other_keys(tmp_home: Path) -> None:
    path = tmp_home / "config.json"
    path.write_text(
        json.dumps({"unrelated": {"foo": "bar"}}), encoding="utf-8"
    )
    enable_telemetry(endpoint="https://example.invalid/events")
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["unrelated"] == {"foo": "bar"}
    assert raw["telemetry"]["enabled"] is True


def test_emit_noop_when_disabled(
    tmp_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Any] = []

    def fake_post(*a: Any, **kw: Any) -> Any:
        calls.append((a, kw))

    monkeypatch.setattr(httpx, "post", fake_post)
    event = TelemetryEvent(name="scan.run", install_id="test-id")
    assert emit(event, blocking=True) is False
    assert calls == []


def test_emit_dispatches_when_enabled(
    tmp_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_telemetry(endpoint="https://example.invalid/events")
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, *, json: dict, timeout: float) -> Any:
        calls.append({"url": url, "json": json, "timeout": timeout})

        class _Resp:
            status_code = 200

        return _Resp()

    monkeypatch.setattr(httpx, "post", fake_post)
    event = TelemetryEvent(name="scan.run", install_id=load_config().install_id or "x")
    assert emit(event, blocking=True) is True
    assert len(calls) == 1
    assert calls[0]["url"] == "https://example.invalid/events"
    assert calls[0]["timeout"] == 0.5


def test_emit_swallows_transport_errors(
    tmp_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_telemetry(endpoint="https://example.invalid/events")

    def boom(*a: Any, **kw: Any) -> Any:
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(httpx, "post", boom)
    event = TelemetryEvent(name="scan.run", install_id="test")
    # Must not raise.
    emit(event, blocking=True)


def test_payload_only_contains_allowlisted_keys() -> None:
    event = TelemetryEvent(
        name="install.success",
        install_id="uuid-1234",
        duration_ms=42,
        result="ok",
    )
    payload = event.to_payload()
    forbidden = {"path", "agent", "tool", "name_slug", "hostname", "user", "cwd"}
    assert forbidden.isdisjoint(payload.keys())
    assert set(payload.keys()).issubset(
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


def test_payload_drops_none_values() -> None:
    event = TelemetryEvent(name="cli.invoke", install_id="uuid")
    payload = event.to_payload()
    assert "duration_ms" not in payload
    assert "result" not in payload
    assert payload["name"] == "cli.invoke"
    assert payload["install_id"] == "uuid"


def test_build_event_filters_extra_keys(tmp_home: Path) -> None:
    event = telemetry.build_event(
        "scan.run",
        install_id="id",
        duration_ms=100,
        result="ok",
        path="/secret/path",  # type: ignore[arg-type]
    )
    payload = event.to_payload()
    assert "path" not in payload
    assert payload["duration_ms"] == 100


def test_schema_description_is_valid_json() -> None:
    parsed = json.loads(schema_description())
    assert "name" in parsed
    assert "install_id" in parsed
