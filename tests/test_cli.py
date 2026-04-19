"""CLI smoke tests using Typer's runner."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from grok_install.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "grok-install" in result.stdout


def test_init_creates_yaml(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", str(tmp_path), "--name", "hello-agent"])
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "grok-install.yaml").exists()


def test_init_refuses_overwrite(tmp_path: Path) -> None:
    (tmp_path / "grok-install.yaml").write_text("already here")
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 1


def test_validate_ok(fixtures_dir: Path) -> None:
    result = runner.invoke(app, ["validate", str(fixtures_dir / "valid.yaml")])
    assert result.exit_code == 0


def test_validate_unknown_tool_fails(fixtures_dir: Path) -> None:
    result = runner.invoke(app, ["validate", str(fixtures_dir / "bad_unknown_tool.yaml")])
    assert result.exit_code == 1


def test_scan_ok(fixtures_dir: Path) -> None:
    result = runner.invoke(app, ["scan", str(fixtures_dir / "valid.yaml")])
    assert result.exit_code == 0


def test_run_dry(fixtures_dir: Path) -> None:
    result = runner.invoke(
        app, ["run", str(fixtures_dir / "valid.yaml"), "--dry-run", "--prompt", "hi"]
    )
    assert result.exit_code == 0
    assert "dry-run" in result.stdout


def test_deploy_docker(fixtures_dir: Path, tmp_path: Path) -> None:
    # copy fixture into tmp_path so deploy writes there
    src = (fixtures_dir / "valid.yaml").read_text()
    (tmp_path / "grok-install.yaml").write_text(src)
    result = runner.invoke(app, ["deploy", str(tmp_path), "--target", "docker"])
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "Dockerfile").exists()
    assert (tmp_path / "docker-compose.yaml").exists()


def test_publish_prints_json(fixtures_dir: Path) -> None:
    result = runner.invoke(app, ["publish", str(fixtures_dir / "valid.yaml")])
    assert result.exit_code == 0
    assert "\"name\": \"valid-sample\"" in result.stdout


def test_validate_json_ok(fixtures_dir: Path) -> None:
    result = runner.invoke(app, ["validate", str(fixtures_dir / "valid.yaml"), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["kind"] == "validation"
    assert payload["ok"] is True
    assert payload["schema_version"] == "1"
    assert payload["issues"] == []


def test_validate_json_unknown_tool(fixtures_dir: Path) -> None:
    result = runner.invoke(
        app, ["validate", str(fixtures_dir / "bad_unknown_tool.yaml"), "--json"]
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["kind"] == "validation"
    assert payload["ok"] is False
    assert any(i["code"] == "unknown-tool" for i in payload["issues"])


def test_validate_json_parse_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate", str(tmp_path), "--json"])
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["kind"] == "parse-error"
    assert payload["ok"] is False
    assert "message" in payload


def test_scan_json_ok(fixtures_dir: Path) -> None:
    result = runner.invoke(app, ["scan", str(fixtures_dir / "valid.yaml"), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["kind"] == "scan"
    assert payload["ok"] is True
    assert payload["schema_version"] == "1"
    assert any(f["code"] == "scan-clean" for f in payload["findings"])


def test_scan_json_blocked_tool(fixtures_dir: Path) -> None:
    result = runner.invoke(
        app, ["scan", str(fixtures_dir / "blocked_tool.yaml"), "--json"]
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["kind"] == "scan"
    assert payload["ok"] is False
    assert any(f["severity"] == "red" for f in payload["findings"])


def test_scan_json_parse_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["scan", str(tmp_path), "--json"])
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["kind"] == "parse-error"
    assert payload["ok"] is False
