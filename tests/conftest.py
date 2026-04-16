"""Shared fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from grok_install.core.models import GrokInstallConfig
from grok_install.core.parser import load_config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def valid_config() -> GrokInstallConfig:
    return load_config(FIXTURES / "valid.yaml")


@pytest.fixture
def swarm_config() -> GrokInstallConfig:
    return load_config(FIXTURES / "swarm.yaml")


class StubTransport:
    """In-memory stub for GrokClient's transport."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat_completion(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("stub transport exhausted")
        return self._responses.pop(0)


@pytest.fixture
def stub_transport_factory():
    return StubTransport
