"""Schema + semantic validation that runs after Pydantic parsing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from grok_install.core.models import GrokInstallConfig
from grok_install.core.registry import is_builtin_tool

Level = Literal["info", "warn", "error"]


@dataclass
class ValidationIssue:
    level: Level
    code: str
    message: str
    path: str = ""

    def marker(self) -> str:
        return {"info": "ℹ", "warn": "⚠", "error": "✖"}[self.level]


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    def add(self, level: Level, code: str, message: str, path: str = "") -> None:
        self.issues.append(ValidationIssue(level, code, message, path))

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "warn"]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_config(config: GrokInstallConfig) -> ValidationReport:
    """Semantic checks that go beyond Pydantic field validation."""

    report = ValidationReport()
    declared_tool_names = {t.name for t in config.tools}

    for agent_name, agent in config.agents.items():
        for tool in agent.tools:
            if tool in declared_tool_names:
                continue
            if is_builtin_tool(tool):
                continue
            report.add(
                "error",
                "unknown-tool",
                f"agent {agent_name!r} references unknown tool {tool!r}; "
                "declare it under tools: or use a built-in name",
                path=f"agents.{agent_name}.tools",
            )

    for tool in config.tools:
        if tool.permission and tool.permission not in config.runtime.permissions:
            report.add(
                "error",
                "missing-permission",
                f"tool {tool.name!r} needs permission {tool.permission!r} but "
                "it is not listed under runtime.permissions",
                path=f"tools.{tool.name}",
            )

    if config.runtime.type == "x-bot":
        if "x.read" not in config.runtime.permissions:
            report.add(
                "warn",
                "xbot-missing-read",
                "x-bot runtime usually needs 'x.read' permission",
                path="runtime.permissions",
            )

    if (
        config.safety.safety_profile == "research"
        and not config.safety.verified_by_grok
    ):
        report.add(
            "warn",
            "research-unverified",
            "research profile is enabled but verified_by_grok is false — "
            "reviewers will flag this",
            path="safety",
        )

    if config.promotion.auto_share and config.safety.safety_profile == "strict":
        report.add(
            "warn",
            "promotion-vs-strict",
            "auto_share conflicts with strict safety_profile — disable one",
            path="promotion.auto_share",
        )

    if config.runtime.type == "scheduled" and not config.runtime.schedule:
        report.add(
            "error",
            "schedule-missing",
            "scheduled runtime requires runtime.schedule (cron expression)",
            path="runtime.schedule",
        )

    return report
