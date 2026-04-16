"""Vercel deploy generator."""

from __future__ import annotations

import json
from pathlib import Path

from grok_install.core.models import GrokInstallConfig
from grok_install.deploy.base import DeployArtifact, env_example


class VercelGenerator:
    target = "vercel"

    def artifacts(self, config: GrokInstallConfig) -> list[DeployArtifact]:
        return [
            DeployArtifact(Path("vercel.json"), self._vercel_json()),
            DeployArtifact(Path("api/index.py"), self._api_entry(config)),
            DeployArtifact(Path("requirements.txt"), self._requirements()),
            DeployArtifact(Path(".env.example"), env_example(config)),
        ]

    def instructions(self, config: GrokInstallConfig) -> str:
        return (
            f"# Deploy {config.name} to Vercel\n"
            "1. Install the Vercel CLI: npm i -g vercel\n"
            "2. Copy .env.example to .env and fill in values.\n"
            f"3. Run: vercel env add {config.llm.api_key_env}\n"
            "4. Run: vercel --prod\n"
            "Your agent is now live at https://<your-project>.vercel.app/api\n"
        )

    @staticmethod
    def _vercel_json() -> str:
        return json.dumps(
            {
                "version": 2,
                "builds": [
                    {"src": "api/index.py", "use": "@vercel/python"},
                ],
                "routes": [
                    {"src": "/(.*)", "dest": "/api/index.py"},
                ],
            },
            indent=2,
        ) + "\n"

    @staticmethod
    def _api_entry(config: GrokInstallConfig) -> str:
        return f'''"""Vercel Python entrypoint for {config.name}."""

from http.server import BaseHTTPRequestHandler
import json
import os

from grok_install import load_config
from grok_install.runtime.agent import AgentRunner
from grok_install.runtime.client import GrokClient
from grok_install.runtime.tools import ToolExecutor, ToolRegistry
from grok_install.safety.scanner import RuntimeSafetyGate


class handler(BaseHTTPRequestHandler):  # noqa: N801 - Vercel convention
    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(length) or b"{{}}")
        user_input = body.get("input", "")

        config = load_config(os.environ.get("GROK_CONFIG", "grok-install.yaml"))
        client = GrokClient.from_config(config.llm)
        gate = RuntimeSafetyGate.from_config(config, auto_approve=False)
        registry = ToolRegistry.from_config(config)
        executor = ToolExecutor(registry=registry, gate=gate)
        runner = AgentRunner(
            config,
            next(iter(config.agents)),
            client=client,
            executor=executor,
        )
        result = runner.run(user_input)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({{"output": result.output}}).encode())
'''

    @staticmethod
    def _requirements() -> str:
        return "grok-install[xai]>=0.1.0\n"
