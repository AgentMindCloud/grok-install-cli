"""Railway deploy generator."""

from __future__ import annotations

from pathlib import Path

from grok_install.core.models import GrokInstallConfig
from grok_install.deploy.base import DeployArtifact, env_example


class RailwayGenerator:
    target = "railway"

    def artifacts(self, config: GrokInstallConfig) -> list[DeployArtifact]:
        return [
            DeployArtifact(Path("railway.toml"), self._railway_toml()),
            DeployArtifact(Path("Procfile"), "web: python -m grok_install run .\n"),
            DeployArtifact(Path("requirements.txt"), "grok-install[xai]>=0.1.0\n"),
            DeployArtifact(Path(".env.example"), env_example(config)),
        ]

    def instructions(self, config: GrokInstallConfig) -> str:
        return (
            f"# Deploy {config.name} to Railway\n"
            "1. Install the Railway CLI: npm i -g @railway/cli\n"
            "2. railway login\n"
            f"3. railway variables set {config.llm.api_key_env}=...\n"
            "4. railway up\n"
        )

    @staticmethod
    def _railway_toml() -> str:
        return (
            "[build]\n"
            'builder = "NIXPACKS"\n\n'
            "[deploy]\n"
            'startCommand = "python -m grok_install run ."\n'
            "restartPolicyType = \"ON_FAILURE\"\n"
            "restartPolicyMaxRetries = 3\n"
        )
