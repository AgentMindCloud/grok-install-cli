"""Swarm-specific safety scanner tests."""

from __future__ import annotations

from pathlib import Path

from grok_install.core.models import (
    AgentDefinition,
    GrokInstallConfig,
    IntelligenceLayer,
    LLMConfig,
    SafetyConfig,
    ToolParameterSchema,
    ToolSchema,
)
from grok_install.safety.scanner import scan_config, scan_path


def _obj_schema() -> ToolParameterSchema:
    return ToolParameterSchema(type="object", properties={})


def test_existing_swarm_fixture_scans_clean(fixtures_dir: Path) -> None:
    report = scan_path(fixtures_dir / "swarm.yaml")
    assert report.ok, [f.code for f in report.reds]


def test_cycle_fixture_produces_red(fixtures_dir: Path) -> None:
    report = scan_path(fixtures_dir / "swarm_cycle.yaml")
    assert not report.ok
    assert any(f.code == "swarm-cycle" for f in report.reds)


def test_multiple_agents_without_swarm_flag_is_red() -> None:
    config = GrokInstallConfig(
        name="demo",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        intelligence=IntelligenceLayer(multi_agent_swarm=False),
        agents={
            "a": AgentDefinition(description="a"),
            "b": AgentDefinition(description="b"),
        },
    )
    report = scan_config(config)
    assert any(f.code == "swarm-flag-missing" for f in report.reds)


def test_fanout_yellow() -> None:
    agents = {
        "root": AgentDefinition(
            description="fan-out",
            handoff=["a", "b", "c", "d", "e", "f"],
        ),
    }
    for name in ["a", "b", "c", "d", "e", "f"]:
        agents[name] = AgentDefinition(description=name)
    config = GrokInstallConfig(
        name="fanout",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        intelligence=IntelligenceLayer(multi_agent_swarm=True),
        agents=agents,
    )
    report = scan_config(config)
    assert any(f.code == "swarm-fanout" for f in report.yellows)


def test_swarm_too_large_yellow() -> None:
    agents = {
        f"agent_{i}": AgentDefinition(description=f"agent {i}") for i in range(17)
    }
    # Build a chain so we have a root and no orphans.
    names = list(agents)
    for i in range(len(names) - 1):
        agents[names[i]] = AgentDefinition(
            description=f"agent {i}", handoff=[names[i + 1]]
        )
    config = GrokInstallConfig(
        name="big-swarm",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        intelligence=IntelligenceLayer(multi_agent_swarm=True),
        agents=agents,
    )
    report = scan_config(config)
    assert any(f.code == "swarm-too-large" for f in report.yellows)


def test_privilege_escalation_balanced_is_red() -> None:
    config = GrokInstallConfig(
        name="esc",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        intelligence=IntelligenceLayer(multi_agent_swarm=True),
        safety=SafetyConfig(safety_profile="balanced"),
        tools=[
            ToolSchema(
                name="poster",
                description="posts to x",
                parameters=_obj_schema(),
                permission="x.write",
            ),
        ],
        agents={
            "reader": AgentDefinition(description="reader", handoff=["writer"]),
            "writer": AgentDefinition(description="writer", tools=["poster"]),
        },
    )
    report = scan_config(config)
    assert any(f.code == "swarm-privilege-escalation" for f in report.reds)


def test_privilege_escalation_strict_with_approval_is_clean() -> None:
    config = GrokInstallConfig(
        name="safe-esc",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        intelligence=IntelligenceLayer(multi_agent_swarm=True),
        safety=SafetyConfig(
            safety_profile="strict",
            require_human_approval=["poster", "post_thread", "reply_to_mention", "post_image"],
        ),
        tools=[
            ToolSchema(
                name="poster",
                description="posts to x",
                parameters=_obj_schema(),
                permission="x.write",
            ),
        ],
        agents={
            "reader": AgentDefinition(description="reader", handoff=["writer"]),
            "writer": AgentDefinition(description="writer", tools=["poster"]),
        },
    )
    report = scan_config(config)
    assert not any(f.code == "swarm-privilege-escalation" for f in report.reds)


def test_orphan_agent_yellow() -> None:
    config = GrokInstallConfig(
        name="orphan",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        intelligence=IntelligenceLayer(multi_agent_swarm=True),
        agents={
            "root": AgentDefinition(description="root", handoff=["child"]),
            "child": AgentDefinition(description="child"),
            "loner": AgentDefinition(description="unreachable"),
        },
    )
    report = scan_config(config)
    assert any(
        f.code == "swarm-orphan-agent" and "loner" in f.message for f in report.yellows
    )


def test_single_agent_never_triggers_swarm_findings(fixtures_dir: Path) -> None:
    report = scan_path(fixtures_dir / "valid.yaml")
    swarm_codes = {
        "swarm-flag-missing",
        "swarm-cycle",
        "swarm-fanout",
        "swarm-orphan-agent",
        "swarm-privilege-escalation",
    }
    assert not any(f.code in swarm_codes for f in report.findings)
