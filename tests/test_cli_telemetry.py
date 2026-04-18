"""Tests for the CLI `telemetry` command group."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from grok_install.cli import app
from grok_install.telemetry.config import (
    ENV_CONFIG_DIR,
    ENV_KILL_SWITCH,
    enable_telemetry,
    load_config,
)


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv(ENV_CONFIG_DIR, str(tmp_path))
    monkeypatch.delenv(ENV_KILL_SWITCH, raising=False)
    return CliRunner()


def test_status_default_shows_disabled(
    runner: CliRunner, tmp_path: Path
) -> None:
    result = runner.invoke(app, ["telemetry", "status"])
    assert result.exit_code == 0
    assert "disabled" in result.stdout
    assert "event schema" in result.stdout


def test_enable_requires_endpoint(runner: CliRunner) -> None:
    result = runner.invoke(app, ["telemetry", "enable"])
    assert result.exit_code != 0


def test_enable_with_yes_flag_persists(
    runner: CliRunner, tmp_path: Path
) -> None:
    result = runner.invoke(
        app,
        [
            "telemetry",
            "enable",
            "--endpoint",
            "https://example.invalid/events",
            "--yes",
        ],
    )
    assert result.exit_code == 0
    assert "telemetry enabled" in result.stdout
    cfg = load_config()
    assert cfg.enabled is True
    assert cfg.install_id is not None
    raw = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert raw["telemetry"]["enabled"] is True


def test_disable_wipes_state(runner: CliRunner, tmp_path: Path) -> None:
    enable_telemetry(endpoint="https://example.invalid/events")
    result = runner.invoke(app, ["telemetry", "disable"])
    assert result.exit_code == 0
    cfg = load_config()
    assert cfg.enabled is False
    assert cfg.install_id is None


def test_kill_switch_causes_no_network_on_scan(
    runner: CliRunner,
    tmp_path: Path,
    fixtures_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_telemetry(endpoint="https://example.invalid/events")
    monkeypatch.setenv(ENV_KILL_SWITCH, "0")

    calls: list[Any] = []

    def fake_post(*a: Any, **kw: Any) -> Any:
        calls.append((a, kw))

    monkeypatch.setattr(httpx, "post", fake_post)

    result = runner.invoke(app, ["scan", str(fixtures_dir / "valid.yaml")])
    assert result.exit_code == 0
    assert calls == []
