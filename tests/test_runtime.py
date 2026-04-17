"""Runtime: tool executor, agent runner, swarm."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from grok_install.core.models import GrokInstallConfig
from grok_install.core.parser import load_config
from grok_install.runtime.agent import AgentRunner
from grok_install.runtime.client import GrokClient
from grok_install.runtime.memory import MemoryStore
from grok_install.runtime.swarm import SwarmOrchestrator
from grok_install.runtime.tools import (
    RateLimitExceeded,
    ToolExecutor,
    ToolNotFound,
    ToolRegistry,
)
from grok_install.safety.scanner import RuntimeSafetyGate


def _make_executor(config: GrokInstallConfig, *, auto_approve: bool = True) -> ToolExecutor:
    registry = ToolRegistry.from_config(config)
    gate = RuntimeSafetyGate.from_config(config, auto_approve=auto_approve)
    return ToolExecutor(registry=registry, gate=gate)


def test_registry_resolves_builtins(valid_config: GrokInstallConfig) -> None:
    registry = ToolRegistry.from_config(valid_config)
    assert "read_file" in registry.schemas
    assert "web_search" in registry.schemas


def test_registry_rejects_unknown_tool(fixtures_dir: Path) -> None:
    with pytest.raises(ToolNotFound):
        config = load_config(fixtures_dir / "bad_unknown_tool.yaml")
        ToolRegistry.from_config(config)


def test_registry_rejects_blocked_tool(fixtures_dir: Path) -> None:
    from grok_install.runtime.tools import ToolBlocked

    config = load_config(fixtures_dir / "blocked_tool.yaml")
    # mass_dm is a hard-blocked name even if the user lists it.
    with pytest.raises((ToolBlocked, ToolNotFound)):
        ToolRegistry.from_config(config)


def test_executor_dry_runs_when_no_handler(valid_config: GrokInstallConfig) -> None:
    executor = _make_executor(valid_config)
    result = executor.execute("read_file", {"path": "README.md"})
    assert '"dry-run"' in result or 'dry-run' in result


def test_executor_runs_handler(valid_config: GrokInstallConfig) -> None:
    executor = _make_executor(valid_config)
    executor.registry.register_handler("read_file", lambda args: f"read: {args['path']}")
    out = executor.execute("read_file", {"path": "README.md"})
    assert out == "read: README.md"


def test_executor_parses_json_string_args(valid_config: GrokInstallConfig) -> None:
    executor = _make_executor(valid_config)
    executor.registry.register_handler("web_search", lambda args: args["query"])
    out = executor.execute("web_search", json.dumps({"query": "grok"}))
    assert out == "grok"


def test_executor_rate_limits(fixtures_dir: Path) -> None:
    config = load_config(fixtures_dir / "valid.yaml")
    config.agents["default"].tools.append("post_thread")
    config.safety.require_human_approval = ["post_thread"]
    executor = _make_executor(config, auto_approve=True)
    executor.registry.register_handler("post_thread", lambda args: "ok")
    # post_thread rate limit is 4 per hour
    for _ in range(4):
        executor.execute("post_thread", {"posts": ["hi"]})
    with pytest.raises(RateLimitExceeded):
        executor.execute("post_thread", {"posts": ["hi"]})


def test_executor_rejects_unknown_tool(valid_config: GrokInstallConfig) -> None:
    executor = _make_executor(valid_config)
    with pytest.raises(ToolNotFound):
        executor.execute("totally_unknown_tool", {})


def test_agent_runner_returns_simple_output(
    valid_config: GrokInstallConfig, stub_transport_factory
) -> None:
    transport = stub_transport_factory([
        {"choices": [{"message": {"content": "hello human", "tool_calls": []}}]},
    ])
    client = GrokClient(valid_config.llm, transport=transport)
    executor = _make_executor(valid_config)
    runner = AgentRunner(valid_config, "default", client=client, executor=executor)
    result = runner.run("hi")
    assert result.output == "hello human"
    assert result.turns == 1


def test_agent_runner_runs_tool_loop(
    valid_config: GrokInstallConfig, stub_transport_factory
) -> None:
    transport = stub_transport_factory(
        [
            {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": json.dumps({"path": "R.md"}),
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {
                "choices": [
                    {"message": {"content": "done", "tool_calls": []}}
                ]
            },
        ]
    )
    client = GrokClient(valid_config.llm, transport=transport)
    executor = _make_executor(valid_config)
    executor.registry.register_handler("read_file", lambda args: f"<{args['path']}>")
    runner = AgentRunner(valid_config, "default", client=client, executor=executor)
    result = runner.run("hi")
    assert result.output == "done"
    assert len(result.tool_calls) == 1
    assert result.turns == 2


def test_agent_runner_respects_max_turns(
    valid_config: GrokInstallConfig, stub_transport_factory
) -> None:
    tool_call = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "x",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps({"path": "a"}),
                            },
                        }
                    ],
                }
            }
        ]
    }
    transport = stub_transport_factory([tool_call] * 20)
    client = GrokClient(valid_config.llm, transport=transport)
    executor = _make_executor(valid_config)
    executor.registry.register_handler("read_file", lambda args: "ok")
    runner = AgentRunner(valid_config, "default", client=client, executor=executor)
    result = runner.run("hi")
    # intelligence.max_turns_per_session is 5 in fixture
    assert result.turns == 5


def test_swarm_handoff(
    swarm_config: GrokInstallConfig, stub_transport_factory
) -> None:
    triage_transport = stub_transport_factory(
        [
            {
                "choices": [
                    {
                        "message": {
                            "content": "routing",
                            "tool_calls": [
                                {
                                    "id": "h",
                                    "type": "function",
                                    "function": {
                                        "name": "handoff_to",
                                        "arguments": json.dumps({"agent": "researcher"}),
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    )
    researcher_transport = stub_transport_factory(
        [{"choices": [{"message": {"content": "research done", "tool_calls": []}}]}]
    )
    triage_client = GrokClient(swarm_config.llm, transport=triage_transport)
    researcher_client = GrokClient(swarm_config.llm, transport=researcher_transport)
    triage_executor = _make_executor(swarm_config)
    researcher_executor = _make_executor(swarm_config)
    runners = {
        "triage": AgentRunner(
            swarm_config,
            "triage",
            client=triage_client,
            executor=triage_executor,
        ),
        "researcher": AgentRunner(
            swarm_config,
            "researcher",
            client=researcher_client,
            executor=researcher_executor,
        ),
    }
    swarm = SwarmOrchestrator(swarm_config, runners)
    trace = swarm.run("go")
    assert [name for name, _ in trace.hops] == ["triage", "researcher"]
    assert trace.final_output == "research done"


def test_memory_round_trip(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "mem.db")
    store.save("a", "long_term", "k", {"v": 1})
    assert store.recall("a", "long_term", "k") == {"v": 1}
    store.save("a", "session", "x", "s")
    assert store.recall("a", "session", "x") == "s"
    store.close_session("a")
    assert store.recall("a", "session", "x") is None
    assert store.recall("a", "long_term", "k") == {"v": 1}
    store.close()


def test_memory_rejects_bad_scope(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "mem.db")
    with pytest.raises(ValueError):
        store.save("a", "nope", "k", "v")
    store.close()
