"""Pre-install safety scanner + runtime approval gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from grok_install.core.models import GrokInstallConfig
from grok_install.safety.rules import (
    BLOCKED_PATTERNS,
    BLOCKED_TOOLS,
    HIGH_RISK_PERMISSIONS,
    REQUIRE_APPROVAL_DEFAULT,
    SENSITIVE_ENV_PREFIXES,
    SWARM_MAX_AGENT_COUNT,
    SWARM_MAX_HANDOFF_FANOUT,
    SWARM_WRITE_PERMISSIONS,
    VOICE_MAX_RECORDING_SECONDS_WARN,
    VOICE_PERMISSIONS,
)

Severity = Literal["green", "yellow", "red"]


@dataclass
class Finding:
    severity: Severity
    code: str
    message: str
    path: str = ""

    def marker(self) -> str:
        return {"green": "✓", "yellow": "!", "red": "✖"}[self.severity]


@dataclass
class SafetyReport:
    findings: list[Finding] = field(default_factory=list)

    def add(self, severity: Severity, code: str, message: str, path: str = "") -> None:
        self.findings.append(Finding(severity, code, message, path))

    @property
    def reds(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "red"]

    @property
    def yellows(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "yellow"]

    @property
    def greens(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "green"]

    @property
    def ok(self) -> bool:
        return not self.reds

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 1


def scan_config(config: GrokInstallConfig, *, raw_text: str | None = None) -> SafetyReport:
    """Run the full pre-install scan."""

    report = SafetyReport()

    _scan_tools(config, report)
    _scan_permissions(config, report)
    _scan_profile(config, report)
    _scan_env(config, report)
    _scan_rate_limits(config, report)
    _scan_approval_flags(config, report)
    _scan_swarm(config, report)
    _scan_voice(config, report)
    if raw_text is not None:
        _scan_raw_text(raw_text, report)

    if report.ok:
        report.add("green", "scan-clean", "no red-level findings; config looks safe")
    return report


def scan_path(path: str | Path) -> SafetyReport:
    """Load and scan a config on disk."""

    from grok_install.core.parser import _load_raw  # local import to avoid cycles

    data, primary = _load_raw(Path(path))
    from grok_install.core.parser import parse_config

    config = parse_config(data, source=primary)
    raw_text = primary.read_text(encoding="utf-8")
    return scan_config(config, raw_text=raw_text)


def _scan_tools(config: GrokInstallConfig, report: SafetyReport) -> None:
    seen: set[str] = set()
    for tool in config.tools:
        seen.add(tool.name)
        if tool.name in BLOCKED_TOOLS:
            report.add(
                "red",
                "blocked-tool",
                f"tool {tool.name!r} is on the hard-block list",
                path=f"tools.{tool.name}",
            )
    for agent_name, agent in config.agents.items():
        for tool in agent.tools:
            if tool in BLOCKED_TOOLS:
                report.add(
                    "red",
                    "blocked-tool-in-agent",
                    f"agent {agent_name!r} references blocked tool {tool!r}",
                    path=f"agents.{agent_name}.tools",
                )
    for tool in config.tools:
        if tool.parameters.type != "object":
            report.add(
                "yellow",
                "tool-params-not-object",
                f"tool {tool.name!r} parameters should be an object schema",
                path=f"tools.{tool.name}.parameters",
            )


def _scan_permissions(config: GrokInstallConfig, report: SafetyReport) -> None:
    perms = set(config.runtime.permissions)
    high = perms & HIGH_RISK_PERMISSIONS
    if high and config.safety.safety_profile == "strict":
        report.add(
            "yellow",
            "strict-high-risk-perms",
            "strict profile with high-risk permissions: "
            + ", ".join(sorted(high)),
            path="runtime.permissions",
        )
    if "shell.exec" in perms and config.safety.safety_profile != "strict":
        report.add(
            "yellow",
            "shell-exec-loose-profile",
            "shell.exec is enabled without strict profile — sandbox the host!",
            path="runtime.permissions",
        )


def _scan_profile(config: GrokInstallConfig, report: SafetyReport) -> None:
    if not config.safety.safety_profile:
        report.add(
            "red",
            "profile-missing",
            "safety_profile must be set (strict | balanced | research)",
            path="safety.safety_profile",
        )


def _scan_env(config: GrokInstallConfig, report: SafetyReport) -> None:
    for key, value in config.env.items():
        lowered = value.lower()
        for prefix in SENSITIVE_ENV_PREFIXES:
            if lowered.startswith(prefix):
                report.add(
                    "red",
                    "hardcoded-secret",
                    f"env.{key} looks like a real secret ({prefix}...) — remove it",
                    path=f"env.{key}",
                )


def _scan_rate_limits(config: GrokInstallConfig, report: SafetyReport) -> None:
    for tool in config.tools:
        if (tool.permission or "").endswith(".write") and tool.rate_limit is None:
            if tool.name not in config.safety.rate_limits:
                report.add(
                    "yellow",
                    "missing-rate-limit",
                    f"writing tool {tool.name!r} has no rate_limit; declare one",
                    path=f"tools.{tool.name}.rate_limit",
                )


def _scan_approval_flags(config: GrokInstallConfig, report: SafetyReport) -> None:
    required = set(REQUIRE_APPROVAL_DEFAULT)
    declared = set(config.safety.require_human_approval)
    missing = required & set(_all_tool_names(config)) - declared
    for name in missing:
        report.add(
            "red",
            "needs-approval",
            f"tool {name!r} must be listed in safety.require_human_approval",
            path="safety.require_human_approval",
        )


def _all_tool_names(config: GrokInstallConfig) -> list[str]:
    names = {t.name for t in config.tools}
    for agent in config.agents.values():
        names.update(agent.tools)
    return list(names)


def _scan_swarm(config: GrokInstallConfig, report: SafetyReport) -> None:
    agents = config.agents
    if not agents:
        return

    agent_count = len(agents)
    if agent_count > 1 and not config.intelligence.multi_agent_swarm:
        report.add(
            "red",
            "swarm-flag-missing",
            "multiple agents declared but intelligence.multi_agent_swarm is false",
            path="intelligence.multi_agent_swarm",
        )

    if agent_count > SWARM_MAX_AGENT_COUNT:
        report.add(
            "yellow",
            "swarm-too-large",
            f"{agent_count} agents declared (max recommended {SWARM_MAX_AGENT_COUNT})",
            path="agents",
        )

    for agent_name, agent in agents.items():
        for target in agent.handoff:
            if target not in agents:
                report.add(
                    "red",
                    "swarm-handoff-unknown",
                    f"agent {agent_name!r} hands off to unknown agent {target!r}",
                    path=f"agents.{agent_name}.handoff",
                )
        if len(agent.handoff) > SWARM_MAX_HANDOFF_FANOUT:
            report.add(
                "yellow",
                "swarm-fanout",
                f"agent {agent_name!r} hands off to {len(agent.handoff)} targets "
                f"(max recommended {SWARM_MAX_HANDOFF_FANOUT})",
                path=f"agents.{agent_name}.handoff",
            )

    cycles = _find_handoff_cycles(agents)
    for cycle in cycles:
        report.add(
            "red",
            "swarm-cycle",
            "handoff cycle: " + " -> ".join(cycle),
            path="agents",
        )

    reachable_from = _reachability(agents)
    if agent_count > 1:
        entry = next(iter(agents))
        reachable_from_entry = reachable_from.get(entry, set()) | {entry}
        for name in agents:
            if name not in reachable_from_entry:
                report.add(
                    "yellow",
                    "swarm-orphan-agent",
                    f"agent {name!r} is not reachable from entry agent {entry!r}",
                    path=f"agents.{name}",
                )

    _scan_swarm_privilege_escalation(config, reachable_from, report)


def _scan_swarm_privilege_escalation(
    config: GrokInstallConfig,
    reachable_from: dict[str, set[str]],
    report: SafetyReport,
) -> None:
    tool_permissions = {t.name: (t.permission or "") for t in config.tools}
    approvals = set(config.safety.require_human_approval)
    strict = config.safety.safety_profile == "strict"

    def agent_write_tools(agent_name: str) -> list[str]:
        agent = config.agents[agent_name]
        return [
            t for t in agent.tools if tool_permissions.get(t, "") in SWARM_WRITE_PERMISSIONS
        ]

    for agent_name, agent in config.agents.items():
        caller_perms = [tool_permissions.get(t, "") for t in agent.tools]
        caller_has_write = any(p in SWARM_WRITE_PERMISSIONS for p in caller_perms)
        if caller_has_write:
            continue
        reachable = reachable_from.get(agent_name, set())
        for target_name in reachable:
            if target_name == agent_name:
                continue
            write_tools = agent_write_tools(target_name)
            if not write_tools:
                continue
            if strict and all(t in approvals for t in write_tools):
                continue
            report.add(
                "red",
                "swarm-privilege-escalation",
                (
                    f"agent {agent_name!r} (no write perms) can hand off to "
                    f"{target_name!r} which calls write tool(s) {write_tools!r}; "
                    "require strict profile + explicit approval"
                ),
                path=f"agents.{agent_name}.handoff",
            )


def _find_handoff_cycles(agents: dict) -> list[list[str]]:
    cycles: list[list[str]] = []
    seen_cycles: set[tuple[str, ...]] = set()

    def walk(start: str, path: list[str]) -> None:
        last = path[-1]
        for nxt in agents[last].handoff:
            if nxt not in agents:
                continue
            if nxt in path:
                cycle = path[path.index(nxt):] + [nxt]
                key = tuple(sorted(cycle[:-1]))
                if key not in seen_cycles:
                    seen_cycles.add(key)
                    cycles.append(cycle)
                continue
            walk(start, path + [nxt])

    for name in agents:
        walk(name, [name])
    return cycles


def _reachability(agents: dict) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {name: set() for name in agents}
    for start in agents:
        stack = [start]
        visited: set[str] = set()
        while stack:
            cur = stack.pop()
            for nxt in agents[cur].handoff:
                if nxt in agents and nxt not in visited:
                    visited.add(nxt)
                    stack.append(nxt)
        out[start] = visited
    return out


def _scan_voice(config: GrokInstallConfig, report: SafetyReport) -> None:
    voice = config.voice
    perms = set(config.runtime.permissions)
    audio_perms_present = bool(perms & VOICE_PERMISSIONS)
    tool_permissions = {t.name: (t.permission or "") for t in config.tools}

    if not voice.enabled:
        if audio_perms_present:
            report.add(
                "red",
                "voice-perm-without-enable",
                "runtime declares audio.* permissions but voice.enabled is false",
                path="runtime.permissions",
            )
        return

    if voice.record_audio and voice.max_recording_seconds is None:
        report.add(
            "red",
            "voice-unbounded-recording",
            "voice.record_audio is true but max_recording_seconds is not set",
            path="voice.max_recording_seconds",
        )

    writer_tools = [
        name for name, perm in tool_permissions.items() if perm in SWARM_WRITE_PERMISSIONS
    ]
    writer_tools += [p for p in perms if p in SWARM_WRITE_PERMISSIONS]
    has_write_surface = bool(writer_tools)

    if config.safety.safety_profile == "research" and has_write_surface:
        report.add(
            "red",
            "voice-research-write-combo",
            "voice enabled with research profile and write permissions — unsafe combo",
            path="voice.enabled",
        )

    if voice.wake_word:
        approvals = set(config.safety.require_human_approval)
        tool_writers = [
            name
            for name, perm in tool_permissions.items()
            if perm in SWARM_WRITE_PERMISSIONS
        ]
        missing = [t for t in tool_writers if t not in approvals]
        if missing:
            report.add(
                "red",
                "voice-wake-write-without-approval",
                "wake_word set but write tools lack require_human_approval: "
                + ", ".join(sorted(missing)),
                path="safety.require_human_approval",
            )

    if (
        voice.max_recording_seconds is not None
        and voice.max_recording_seconds > VOICE_MAX_RECORDING_SECONDS_WARN
    ):
        report.add(
            "yellow",
            "voice-long-recording",
            f"max_recording_seconds={voice.max_recording_seconds} exceeds "
            f"recommended {VOICE_MAX_RECORDING_SECONDS_WARN}s",
            path="voice.max_recording_seconds",
        )

    if voice.store_recordings and config.safety.safety_profile != "strict":
        report.add(
            "yellow",
            "voice-store-loose-profile",
            "voice.store_recordings is true without strict safety profile",
            path="voice.store_recordings",
        )

    if not audio_perms_present:
        report.add(
            "yellow",
            "voice-missing-audio-perm",
            "voice enabled but no audio.* permission in runtime.permissions",
            path="runtime.permissions",
        )


def _scan_raw_text(raw: str, report: SafetyReport) -> None:
    for code, pattern in BLOCKED_PATTERNS.items():
        if pattern.search(raw):
            report.add(
                "red",
                code,
                f"config appears to contain a {code!r} pattern in plaintext",
            )


# --- Runtime gate -----------------------------------------------------------


class ApprovalDenied(PermissionError):
    """Raised when the user (or policy) refuses a tool call."""


ApprovalCallback = Callable[[str, dict[str, Any]], bool]


@dataclass
class ApprovalPolicy:
    """How to handle tools that require human approval."""

    tools: frozenset[str]
    callback: ApprovalCallback | None = None
    auto_approve: bool = False

    def ask(self, name: str, arguments: dict[str, Any]) -> bool:
        if name not in self.tools:
            return True
        if self.auto_approve:
            return True
        if self.callback is None:
            return False
        return bool(self.callback(name, arguments))


@dataclass
class RuntimeSafetyGate:
    """Gate every tool invocation at runtime."""

    config: GrokInstallConfig
    approval: ApprovalPolicy

    @classmethod
    def from_config(
        cls,
        config: GrokInstallConfig,
        *,
        callback: ApprovalCallback | None = None,
        auto_approve: bool = False,
    ) -> RuntimeSafetyGate:
        tools = frozenset(config.safety.require_human_approval) | REQUIRE_APPROVAL_DEFAULT
        return cls(
            config=config,
            approval=ApprovalPolicy(
                tools=tools, callback=callback, auto_approve=auto_approve
            ),
        )

    def check(self, name: str, arguments: dict[str, Any]) -> None:
        if name in BLOCKED_TOOLS:
            raise ApprovalDenied(f"tool {name!r} is on the hard-block list")
        if name in self.config.safety.blocked_tools:
            raise ApprovalDenied(f"tool {name!r} is blocked by config")
        if not self.approval.ask(name, arguments):
            raise ApprovalDenied(f"user denied tool {name!r}")


def require_approval(name: str, arguments: dict[str, Any], gate: RuntimeSafetyGate) -> None:
    """Module-level helper used by integration stubs."""

    gate.check(name, arguments)
