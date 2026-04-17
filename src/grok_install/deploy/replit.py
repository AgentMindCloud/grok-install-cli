"""Replit deploy generator."""

from __future__ import annotations

from pathlib import Path

from grok_install.core.models import GrokInstallConfig
from grok_install.deploy.base import DeployArtifact, env_example


class ReplitGenerator:
    target = "replit"

    def artifacts(self, config: GrokInstallConfig) -> list[DeployArtifact]:
        return [
            DeployArtifact(Path(".replit"), self._replit()),
            DeployArtifact(Path("replit.nix"), self._replit_nix()),
            DeployArtifact(Path("requirements.txt"), "grok-install[xai]>=0.1.0\n"),
            DeployArtifact(Path(".env.example"), env_example(config)),
        ]

    def instructions(self, config: GrokInstallConfig) -> str:
        return (
            f"# Deploy {config.name} to Replit\n"
            "1. Import this repo on https://replit.com\n"
            f"2. Open the Secrets tab and set {config.llm.api_key_env}\n"
            "3. Press Run.\n"
        )

    @staticmethod
    def _replit() -> str:
        return (
            'language = "python3"\n'
            'run = "python -m grok_install run ."\n'
            'entrypoint = "grok-install.yaml"\n'
        )

    @staticmethod
    def _replit_nix() -> str:
        return (
            "{ pkgs }: {\n"
            "  deps = [ pkgs.python311 pkgs.python311Packages.pip ];\n"
            "}\n"
        )
