"""Docker + docker-compose deploy generator."""

from __future__ import annotations

from pathlib import Path

from grok_install.core.models import GrokInstallConfig
from grok_install.deploy.base import DeployArtifact, env_example


class DockerGenerator:
    target = "docker"

    def artifacts(self, config: GrokInstallConfig) -> list[DeployArtifact]:
        return [
            DeployArtifact(Path("Dockerfile"), self._dockerfile()),
            DeployArtifact(Path("docker-compose.yaml"), self._compose(config)),
            DeployArtifact(Path(".dockerignore"), self._dockerignore()),
            DeployArtifact(Path(".env.example"), env_example(config)),
        ]

    def instructions(self, config: GrokInstallConfig) -> str:
        return (
            f"# Deploy {config.name} with Docker\n"
            "1. Copy .env.example to .env and fill in values.\n"
            "2. docker compose build\n"
            "3. docker compose up -d\n"
        )

    @staticmethod
    def _dockerfile() -> str:
        return (
            "FROM python:3.11-slim\n"
            "WORKDIR /app\n"
            "COPY requirements.txt* ./\n"
            "RUN pip install --no-cache-dir 'grok-install[xai]>=0.1.0'\n"
            "COPY . .\n"
            "USER 1000:1000\n"
            'CMD ["python", "-m", "grok_install", "run", "."]\n'
        )

    @staticmethod
    def _compose(config: GrokInstallConfig) -> str:
        return (
            "services:\n"
            f"  {config.name}:\n"
            "    build: .\n"
            "    env_file: .env\n"
            "    restart: unless-stopped\n"
        )

    @staticmethod
    def _dockerignore() -> str:
        return (
            ".git\n"
            ".venv\n"
            "__pycache__\n"
            "*.pyc\n"
            ".env\n"
            "tests\n"
        )
