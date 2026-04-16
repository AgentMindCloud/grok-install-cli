"""Shared types + dispatch for deploy generators."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from grok_install.core.models import GrokInstallConfig


@dataclass
class DeployArtifact:
    """A single file that the generator wants to write."""

    path: Path
    content: str
    overwrite: bool = True


@dataclass
class DeployResult:
    target: str
    written: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    instructions: str = ""


class Generator(Protocol):
    target: str

    def artifacts(self, config: GrokInstallConfig) -> list[DeployArtifact]: ...
    def instructions(self, config: GrokInstallConfig) -> str: ...


def write_artifacts(
    target: str,
    artifacts: list[DeployArtifact],
    root: Path,
    *,
    instructions: str,
    force: bool = False,
) -> DeployResult:
    result = DeployResult(target=target, instructions=instructions)
    for art in artifacts:
        out = root / art.path
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists() and not (art.overwrite or force):
            result.skipped.append(out)
            continue
        out.write_text(art.content, encoding="utf-8")
        result.written.append(out)
    return result


def env_example(config: GrokInstallConfig) -> str:
    keys = {config.llm.api_key_env}
    for tool in config.tools:
        if tool.permission == "x.write":
            keys.update({"X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN"})
        if tool.permission and tool.permission.startswith("github"):
            keys.add("GITHUB_TOKEN")
    lines = ["# Copy to .env and fill in values."]
    for key in sorted(keys):
        lines.append(f"{key}=")
    return "\n".join(lines) + "\n"


def get_generator(name: str) -> Generator:
    from grok_install.deploy.docker import DockerGenerator
    from grok_install.deploy.railway import RailwayGenerator
    from grok_install.deploy.replit import ReplitGenerator
    from grok_install.deploy.vercel import VercelGenerator

    registry: dict[str, type[Generator]] = {
        "vercel": VercelGenerator,
        "railway": RailwayGenerator,
        "docker": DockerGenerator,
        "replit": ReplitGenerator,
    }
    if name not in registry:
        raise KeyError(f"unknown deploy target {name!r}")
    return registry[name]()
