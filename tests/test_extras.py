"""Coverage-targeted tests for paths not exercised by the main suites."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from grok_install.cli import app
from grok_install.core.models import (
    AgentDefinition,
    GrokInstallConfig,
    IntelligenceLayer,
    LLMConfig,
    SafetyConfig,
    ToolParameterSchema,
    ToolSchema,
    XNativeRuntime,
)
from grok_install.core.parser import load_config
from grok_install.integrations.x_api import XPoster
from grok_install.runtime.agent import AgentRunResult
from grok_install.runtime.memory import MemoryStore
from grok_install.runtime.swarm import SwarmOrchestrator
from grok_install.safety.scanner import (
    ApprovalDenied,
    ApprovalPolicy,
    RuntimeSafetyGate,
    scan_path,
)
from grok_install.telemetry.config import (
    ENV_CONFIG_DIR,
    ENV_KILL_SWITCH,
    enable_telemetry,
)

runner = CliRunner()


# --- CLI edge paths ---------------------------------------------------------


def test_cli_scan_red_exits_nonzero(
    fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_CONFIG_DIR, str(tmp_path))
    result = runner.invoke(app, ["scan", str(fixtures_dir / "blocked_tool.yaml")])
    assert result.exit_code == 1


def test_cli_scan_voice_bad_exits_nonzero(
    fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_CONFIG_DIR, str(tmp_path))
    result = runner.invoke(app, ["scan", str(fixtures_dir / "voice_bad.yaml")])
    assert result.exit_code == 1
    assert "voice-unbounded" in result.stdout


def test_cli_scan_swarm_cycle_exits_nonzero(
    fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_CONFIG_DIR, str(tmp_path))
    result = runner.invoke(app, ["scan", str(fixtures_dir / "swarm_cycle.yaml")])
    assert result.exit_code == 1
    assert "swarm-cycle" in result.stdout


def test_cli_test_cmd_is_dry_run(fixtures_dir: Path) -> None:
    result = runner.invoke(app, ["test", str(fixtures_dir / "valid.yaml")])
    assert result.exit_code == 0
    assert "dry-run" in result.stdout


def test_cli_deploy_unknown_target(fixtures_dir: Path, tmp_path: Path) -> None:
    (tmp_path / "grok-install.yaml").write_text(
        (fixtures_dir / "valid.yaml").read_text(), encoding="utf-8"
    )
    result = runner.invoke(
        app, ["deploy", str(tmp_path), "--target", "nonsense"]
    )
    assert result.exit_code == 2


def test_cli_deploy_force_overwrite(fixtures_dir: Path, tmp_path: Path) -> None:
    (tmp_path / "grok-install.yaml").write_text(
        (fixtures_dir / "valid.yaml").read_text(), encoding="utf-8"
    )
    (tmp_path / "Dockerfile").write_text("# placeholder", encoding="utf-8")
    result = runner.invoke(
        app, ["deploy", str(tmp_path), "--target", "docker", "--force"]
    )
    assert result.exit_code == 0
    assert "# placeholder" not in (tmp_path / "Dockerfile").read_text()


def test_cli_validate_on_parse_error(tmp_path: Path) -> None:
    (tmp_path / "grok-install.yaml").write_text(": : not yaml", encoding="utf-8")
    result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == 2


def test_cli_telemetry_enable_refuses_on_non_tty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without --yes and no tty, opt-in must refuse — safer default for scripts."""
    monkeypatch.setenv(ENV_CONFIG_DIR, str(tmp_path))
    monkeypatch.delenv(ENV_KILL_SWITCH, raising=False)
    result = runner.invoke(
        app,
        ["telemetry", "enable", "--endpoint", "https://example.invalid/events"],
    )
    assert result.exit_code == 1
    assert "not a tty" in result.stdout


def test_cli_scan_emits_when_telemetry_enabled(
    fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_CONFIG_DIR, str(tmp_path))
    monkeypatch.delenv(ENV_KILL_SWITCH, raising=False)
    enable_telemetry(endpoint="https://example.invalid/events")

    calls: list[dict] = []

    def fake_post(url: str, *, json: dict, timeout: float) -> Any:
        calls.append({"url": url, "json": json})

        class _R:
            status_code = 200

        return _R()

    monkeypatch.setattr(httpx, "post", fake_post)
    result = runner.invoke(app, ["scan", str(fixtures_dir / "valid.yaml")])
    assert result.exit_code == 0
    # Thread-dispatch can be async; wait briefly by joining the daemon threads.
    import threading

    for t in threading.enumerate():
        if t is not threading.current_thread() and t.daemon:
            t.join(timeout=1.0)
    assert any(c["json"].get("name") == "scan.run" for c in calls)


# --- Scanner / approval edge paths ------------------------------------------


def test_runtime_gate_rejects_config_blocked_tool(fixtures_dir: Path) -> None:
    config = load_config(fixtures_dir / "valid.yaml")
    config.safety.blocked_tools = ["custom_blocked"]
    gate = RuntimeSafetyGate.from_config(config, auto_approve=True)
    with pytest.raises(ApprovalDenied):
        gate.check("custom_blocked", {})


def test_approval_policy_denies_when_callback_false() -> None:
    p = ApprovalPolicy(
        tools=frozenset({"post_thread"}), callback=lambda _n, _a: False
    )
    assert p.ask("post_thread", {"x": 1}) is False


def test_scan_path_on_voice_fixture(fixtures_dir: Path) -> None:
    report = scan_path(fixtures_dir / "voice.yaml")
    assert report.ok


def test_scan_deep_handoff_chain_no_cycle() -> None:
    names = [f"a{i}" for i in range(6)]
    agents = {
        names[i]: AgentDefinition(
            description=f"a{i}",
            handoff=[names[i + 1]] if i + 1 < len(names) else [],
        )
        for i in range(len(names))
    }
    config = GrokInstallConfig(
        name="chain",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        intelligence=IntelligenceLayer(multi_agent_swarm=True),
        agents=agents,
    )
    from grok_install.safety.scanner import scan_config

    report = scan_config(config)
    assert not any(f.code == "swarm-cycle" for f in report.findings)
    assert not any(f.code == "swarm-orphan-agent" for f in report.findings)


def test_scan_unknown_handoff_target_is_red() -> None:
    # Bypass Pydantic's validator by constructing from a dict with valid refs,
    # then mutating post-construction to point at a missing agent.
    config = GrokInstallConfig(
        name="unknown",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        intelligence=IntelligenceLayer(multi_agent_swarm=True),
        agents={
            "root": AgentDefinition(description="x", handoff=["child"]),
            "child": AgentDefinition(description="x"),
        },
    )
    config.agents["root"].handoff = ["ghost"]
    from grok_install.safety.scanner import scan_config

    report = scan_config(config)
    assert any(f.code == "swarm-handoff-unknown" for f in report.reds)


# --- Memory store coverage --------------------------------------------------


def test_memory_store_roundtrip() -> None:
    store = MemoryStore(":memory:")
    store.save("agent", "session", "k", {"v": 1})
    store.save("agent", "long_term", "k", "stable")
    assert store.recall("agent", "session", "k") == {"v": 1}
    assert store.recall("agent", "long_term", "k") == "stable"
    assert store.recall("agent", "session", "missing") is None

    entries = store.list_entries("agent")
    assert len(entries) == 2

    entries_session = store.list_entries("agent", scope="session")
    assert len(entries_session) == 1
    assert entries_session[0].scope == "session"

    store.close_session("agent")
    assert store.recall("agent", "session", "k") is None
    assert store.recall("agent", "long_term", "k") == "stable"

    with pytest.raises(ValueError):
        store.save("agent", "bad_scope", "k", 1)

    store.close()


# --- Swarm runtime cycle guard ---------------------------------------------


class _StubRunner:
    def __init__(self, name: str, output: str, handoff_to: str | None) -> None:
        self.name = name
        self._output = output
        self._handoff = handoff_to

    def run(self, _msg: str) -> AgentRunResult:
        return AgentRunResult(
            output=self._output, messages=[], handoff_to=self._handoff
        )


def test_swarm_orchestrator_cycle_guard() -> None:
    config = GrokInstallConfig(
        name="sw",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        intelligence=IntelligenceLayer(multi_agent_swarm=True),
        agents={
            "a": AgentDefinition(description="a", handoff=["b"]),
            "b": AgentDefinition(description="b", handoff=["a"]),
        },
    )
    runners = {
        "a": _StubRunner("a", "hi from a", handoff_to="b"),
        "b": _StubRunner("b", "hi from b", handoff_to="a"),
    }
    orch = SwarmOrchestrator(config, runners)  # type: ignore[arg-type]
    trace = orch.run("hello")
    assert "cycle guard" in trace.hops[-1][1].output


def test_swarm_orchestrator_unknown_start() -> None:
    config = GrokInstallConfig(
        name="sw",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        intelligence=IntelligenceLayer(multi_agent_swarm=True),
        agents={"a": AgentDefinition(description="a")},
    )
    runners = {"a": _StubRunner("a", "out", handoff_to=None)}
    orch = SwarmOrchestrator(config, runners)  # type: ignore[arg-type]
    with pytest.raises(KeyError):
        orch.run("hi", start="missing")


def test_swarm_orchestrator_requires_flag() -> None:
    config = GrokInstallConfig(
        name="sw",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        agents={
            "a": AgentDefinition(description="a"),
        },
    )
    with pytest.raises(RuntimeError):
        SwarmOrchestrator(config, {"a": _StubRunner("a", "x", None)})  # type: ignore[arg-type]


# --- X API coverage ---------------------------------------------------------


class _HTTPStub:
    def __init__(self) -> None:
        self.posts: list[tuple[str, dict, dict]] = []
        self._next_id = 100

    def post(self, url: str, *, json: dict, headers: dict) -> dict:
        self.posts.append((url, json, headers))
        self._next_id += 1
        return {"data": {"id": str(self._next_id)}}


def test_xposter_thread_with_http_client(fixtures_dir: Path) -> None:
    config = load_config(fixtures_dir / "valid.yaml")
    gate = RuntimeSafetyGate.from_config(config, auto_approve=True)
    http = _HTTPStub()
    poster = XPoster(bearer_token="tok", gate=gate, http=http)
    ids = poster.post_thread(["a", "b"])
    assert ids == ["101", "102"]
    assert len(http.posts) == 2
    # Second post should thread-reply to first.
    assert http.posts[1][1]["reply"]["in_reply_to_tweet_id"] == "101"


def test_xposter_thread_dryrun(fixtures_dir: Path) -> None:
    config = load_config(fixtures_dir / "valid.yaml")
    gate = RuntimeSafetyGate.from_config(config, auto_approve=True)
    poster = XPoster(bearer_token="tok", gate=gate, http=None)
    ids = poster.post_thread(["hello"])
    assert len(ids) == 1
    assert ids[0].startswith("dryrun-")


def test_xposter_reply_to_mention(fixtures_dir: Path) -> None:
    config = load_config(fixtures_dir / "valid.yaml")
    gate = RuntimeSafetyGate.from_config(config, auto_approve=True)
    poster = XPoster(bearer_token="tok", gate=gate, http=_HTTPStub())
    reply_id = poster.reply_to_mention("999", "thanks")
    assert reply_id.isdigit()


def test_xposter_empty_thread_raises(fixtures_dir: Path) -> None:
    config = load_config(fixtures_dir / "valid.yaml")
    gate = RuntimeSafetyGate.from_config(config, auto_approve=True)
    poster = XPoster(bearer_token="tok", gate=gate, http=None)
    with pytest.raises(ValueError):
        poster.post_thread([])


# --- VoiceConfig validators -------------------------------------------------


def test_voice_wake_word_blank_rejected() -> None:
    from grok_install.core.models import VoiceConfig

    with pytest.raises(ValueError):
        VoiceConfig(enabled=True, wake_word="   ")


def test_voice_wake_word_too_long_rejected() -> None:
    from grok_install.core.models import VoiceConfig

    with pytest.raises(ValueError):
        VoiceConfig(enabled=True, wake_word="x" * 65)


def test_voice_wake_word_trims() -> None:
    from grok_install.core.models import VoiceConfig

    v = VoiceConfig(enabled=True, wake_word="  hey grok  ")
    assert v.wake_word == "hey grok"


# --- Validator semantic warnings --------------------------------------------


def test_validator_xbot_missing_read_warn() -> None:
    from grok_install.core.validator import validate_config

    config = GrokInstallConfig(
        name="xbot",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        runtime=XNativeRuntime(type="x-bot", permissions=["x.write"]),
        safety=SafetyConfig(
            safety_profile="strict", require_human_approval=["post_thread"]
        ),
        agents={"default": AgentDefinition(description="x")},
    )
    report = validate_config(config)
    assert any(i.code == "xbot-missing-read" for i in report.warnings)


def test_validator_research_unverified_warn() -> None:
    from grok_install.core.validator import validate_config

    config = GrokInstallConfig(
        name="research-agent",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        safety=SafetyConfig(safety_profile="research", verified_by_grok=False),
        agents={"default": AgentDefinition(description="x")},
    )
    report = validate_config(config)
    assert any(i.code == "research-unverified" for i in report.warnings)


def test_validator_promotion_vs_strict_warn() -> None:
    from grok_install.core.models import PromotionConfig
    from grok_install.core.validator import validate_config

    config = GrokInstallConfig(
        name="promo-agent",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        safety=SafetyConfig(safety_profile="strict"),
        promotion=PromotionConfig(auto_share=True),
        agents={"default": AgentDefinition(description="x")},
    )
    report = validate_config(config)
    assert any(i.code == "promotion-vs-strict" for i in report.warnings)


def test_validator_schedule_missing_error() -> None:
    from grok_install.core.validator import validate_config

    config = GrokInstallConfig(
        name="scheduled-agent",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        runtime=XNativeRuntime(type="scheduled"),
        agents={"default": AgentDefinition(description="x")},
    )
    report = validate_config(config)
    assert any(i.code == "schedule-missing" for i in report.errors)


def test_validator_missing_permission_error() -> None:
    from grok_install.core.validator import validate_config

    config = GrokInstallConfig(
        name="perm",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        runtime=XNativeRuntime(permissions=["fs.read"]),
        tools=[
            ToolSchema(
                name="needs_net",
                description="needs net.write",
                parameters=ToolParameterSchema(type="object", properties={}),
                permission="net.write",
            ),
        ],
        agents={"default": AgentDefinition(description="x")},
    )
    report = validate_config(config)
    assert any(i.code == "missing-permission" for i in report.errors)


# --- Tool executor coverage -------------------------------------------------


def test_tool_executor_dry_run_returns_echo(fixtures_dir: Path) -> None:
    from grok_install.runtime.tools import ToolExecutor, ToolRegistry

    config = load_config(fixtures_dir / "valid.yaml")
    registry = ToolRegistry.from_config(config)
    gate = RuntimeSafetyGate.from_config(config, auto_approve=True)
    executor = ToolExecutor(registry=registry, gate=gate)
    raw = executor.execute("read_file", {"path": "somewhere"})
    import json as _json

    parsed = _json.loads(raw)
    assert parsed["status"] == "dry-run"
    assert parsed["tool"] == "read_file"


def test_tool_executor_string_args_parsed(fixtures_dir: Path) -> None:
    from grok_install.runtime.tools import ToolExecutor, ToolRegistry

    config = load_config(fixtures_dir / "valid.yaml")
    registry = ToolRegistry.from_config(config)
    gate = RuntimeSafetyGate.from_config(config, auto_approve=True)
    executor = ToolExecutor(registry=registry, gate=gate)
    raw = executor.execute("read_file", '{"path": "x"}')
    assert "dry-run" in raw


def test_tool_executor_bad_json_raises(fixtures_dir: Path) -> None:
    from grok_install.runtime.tools import ToolBlocked, ToolExecutor, ToolRegistry

    config = load_config(fixtures_dir / "valid.yaml")
    registry = ToolRegistry.from_config(config)
    gate = RuntimeSafetyGate.from_config(config, auto_approve=True)
    executor = ToolExecutor(registry=registry, gate=gate)
    with pytest.raises(ToolBlocked):
        executor.execute("read_file", "{not json")


def test_tool_executor_unknown_tool_raises(fixtures_dir: Path) -> None:
    from grok_install.runtime.tools import ToolExecutor, ToolNotFound, ToolRegistry

    config = load_config(fixtures_dir / "valid.yaml")
    registry = ToolRegistry.from_config(config)
    gate = RuntimeSafetyGate.from_config(config, auto_approve=True)
    executor = ToolExecutor(registry=registry, gate=gate)
    with pytest.raises(ToolNotFound):
        executor.execute("unknown_tool", {})


def test_tool_executor_handler_exception_returned_as_error(
    fixtures_dir: Path,
) -> None:
    from grok_install.runtime.tools import ToolExecutor, ToolRegistry

    config = load_config(fixtures_dir / "valid.yaml")
    registry = ToolRegistry.from_config(config)
    gate = RuntimeSafetyGate.from_config(config, auto_approve=True)

    def bad_handler(_args: dict) -> str:
        raise RuntimeError("boom")

    registry.register_handler("read_file", bad_handler)
    executor = ToolExecutor(registry=registry, gate=gate)
    raw = executor.execute("read_file", {"path": "x"})
    import json as _json

    parsed = _json.loads(raw)
    assert parsed["status"] == "error"
    assert "boom" in parsed["error"]


def test_tool_executor_rate_limit(fixtures_dir: Path) -> None:
    from grok_install.core.models import RateLimit
    from grok_install.runtime.tools import (
        RateLimitExceeded,
        ToolExecutor,
        ToolRegistry,
    )

    schema = ToolSchema(
        name="custom_tool",
        description="limited",
        parameters=ToolParameterSchema(type="object", properties={}),
        rate_limit=RateLimit(per="minute", max=1),
    )
    config = GrokInstallConfig(
        name="rl",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        safety=SafetyConfig(safety_profile="strict"),
        tools=[schema],
        agents={"default": AgentDefinition(description="x", tools=["custom_tool"])},
    )
    registry = ToolRegistry.from_config(config)
    registry.register_handler("custom_tool", lambda _a: "ok")
    gate = RuntimeSafetyGate.from_config(config, auto_approve=True)
    executor = ToolExecutor(registry=registry, gate=gate)

    first = executor.execute("custom_tool", {})
    assert first == "ok"
    with pytest.raises(RateLimitExceeded):
        executor.execute("custom_tool", {})


# --- CLI install + publish coverage -----------------------------------------


def test_cli_install_scan_failure_path(
    tmp_path: Path, fixtures_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """install() should exit 1 when the downloaded config fails scan."""
    monkeypatch.setenv(ENV_CONFIG_DIR, str(tmp_path))

    cloned_dir = tmp_path / "cloned"
    cloned_dir.mkdir()
    (cloned_dir / "grok-install.yaml").write_text(
        (fixtures_dir / "blocked_tool.yaml").read_text(), encoding="utf-8"
    )

    import grok_install.cli as cli_module
    from grok_install.integrations.github import GitHubTarget

    monkeypatch.setattr(
        cli_module,
        "parse_github_url",
        lambda _url: GitHubTarget(owner="a", repo="b"),
    )
    monkeypatch.setattr(cli_module, "fetch_repo", lambda _url, _dest: cloned_dir)

    result = runner.invoke(
        app, ["install", "https://github.com/a/b", "--dest", str(tmp_path)]
    )
    assert result.exit_code == 1
    assert "scan failed" in result.stdout


def test_cli_install_success_path(
    tmp_path: Path, fixtures_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_CONFIG_DIR, str(tmp_path))

    cloned_dir = tmp_path / "clone"
    cloned_dir.mkdir()
    (cloned_dir / "grok-install.yaml").write_text(
        (fixtures_dir / "valid.yaml").read_text(), encoding="utf-8"
    )

    import grok_install.cli as cli_module
    from grok_install.integrations.github import GitHubTarget

    monkeypatch.setattr(
        cli_module,
        "parse_github_url",
        lambda _url: GitHubTarget(owner="a", repo="b"),
    )
    monkeypatch.setattr(cli_module, "fetch_repo", lambda _url, _dest: cloned_dir)

    result = runner.invoke(
        app, ["install", "https://github.com/a/b", "--dest", str(tmp_path)]
    )
    assert result.exit_code == 0


def test_cli_publish_with_top_level_tools(
    fixtures_dir: Path, tmp_path: Path
) -> None:
    cfg_src = (fixtures_dir / "valid.yaml").read_text()
    (tmp_path / "grok-install.yaml").write_text(
        cfg_src + "\ntools:\n  - name: my_tool\n"
        "    description: demo\n"
        "    parameters:\n      type: object\n      properties: {}\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["publish", str(tmp_path)])
    assert result.exit_code == 0
    assert "my_tool" in result.stdout
