"""Pre-install safety scanner tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from grok_install.core.models import AgentDefinition, GrokInstallConfig, LLMConfig
from grok_install.safety.scanner import (
    ApprovalDenied,
    ApprovalPolicy,
    RuntimeSafetyGate,
    scan_config,
    scan_path,
)


def test_scan_clean_valid(fixtures_dir: Path) -> None:
    report = scan_path(fixtures_dir / "valid.yaml")
    assert report.ok
    assert any(f.code == "scan-clean" for f in report.findings)


def test_scan_hardcoded_secret_in_env() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        GrokInstallConfig(
            name="demo",
            llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
            env={"XAI_API_KEY": "xai-abcdefabcdefabcdefabcdefabcdef1234"},
        )


def test_scan_hardcoded_secret_in_raw_text() -> None:
    config = GrokInstallConfig(
        name="demo",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
    )
    raw = "name: demo\nsecret: xai-abcdefabcdefabcdefabcdef1234abcd\n"
    report = scan_config(config, raw_text=raw)
    assert not report.ok
    assert any("hardcoded" in f.code for f in report.reds)


def test_scan_flags_missing_approval(fixtures_dir: Path) -> None:
    from grok_install.core.parser import load_config

    config = load_config(fixtures_dir / "valid.yaml")
    config.safety.require_human_approval = []
    config.agents["default"].tools.append("post_thread")
    config.tools  # noqa: B018 - touch for coverage
    report = scan_config(config)
    assert any(f.code == "needs-approval" for f in report.reds)


def test_scan_flags_blocked_tool_reference() -> None:
    config = GrokInstallConfig(
        name="demo",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        agents={
            "default": AgentDefinition(description="x", tools=["mass_dm"]),
        },
    )
    report = scan_config(config)
    assert not report.ok
    assert any(f.code == "blocked-tool-in-agent" for f in report.reds)


def test_runtime_gate_denies_blocked_tool(fixtures_dir: Path) -> None:
    from grok_install.core.parser import load_config

    config = load_config(fixtures_dir / "valid.yaml")
    gate = RuntimeSafetyGate.from_config(config, auto_approve=True)
    with pytest.raises(ApprovalDenied):
        gate.check("mass_dm", {})


def test_runtime_gate_denies_without_callback(fixtures_dir: Path) -> None:
    from grok_install.core.parser import load_config

    config = load_config(fixtures_dir / "valid.yaml")
    gate = RuntimeSafetyGate.from_config(config)
    with pytest.raises(ApprovalDenied):
        gate.check("post_thread", {"posts": ["hi"]})


def test_runtime_gate_auto_approve(fixtures_dir: Path) -> None:
    from grok_install.core.parser import load_config

    config = load_config(fixtures_dir / "valid.yaml")
    gate = RuntimeSafetyGate.from_config(config, auto_approve=True)
    gate.check("post_thread", {"posts": ["hi"]})


def test_approval_policy_callback() -> None:
    calls = []

    def cb(name, args):
        calls.append(name)
        return True

    p = ApprovalPolicy(tools=frozenset({"post_thread"}), callback=cb)
    assert p.ask("post_thread", {"posts": ["hi"]})
    assert p.ask("read_file", {"path": "x"})
    assert calls == ["post_thread"]
