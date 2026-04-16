"""Semantic validator tests."""

from __future__ import annotations

from pathlib import Path

from grok_install.core.models import AgentDefinition, GrokInstallConfig, LLMConfig
from grok_install.core.parser import load_config
from grok_install.core.validator import validate_config


def test_valid_config_passes(fixtures_dir: Path) -> None:
    config = load_config(fixtures_dir / "valid.yaml")
    report = validate_config(config)
    assert report.ok


def test_unknown_tool_flagged(fixtures_dir: Path) -> None:
    config = load_config(fixtures_dir / "bad_unknown_tool.yaml")
    report = validate_config(config)
    assert not report.ok
    assert any(i.code == "unknown-tool" for i in report.errors)


def test_scheduled_needs_cron() -> None:
    config = GrokInstallConfig(
        name="demo",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        runtime={"type": "scheduled"},
        agents={"default": AgentDefinition(description="x")},
    )
    report = validate_config(config)
    assert any(i.code == "schedule-missing" for i in report.errors)


def test_research_without_verified_warns() -> None:
    config = GrokInstallConfig(
        name="demo",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        safety={"safety_profile": "research"},
        agents={"default": AgentDefinition(description="x")},
    )
    report = validate_config(config)
    assert any(i.code == "research-unverified" for i in report.warnings)
