"""Integrations: X poster + GitHub fetcher."""

from __future__ import annotations

from pathlib import Path

import pytest

from grok_install.integrations.github import fetch_repo, parse_github_url
from grok_install.integrations.x_api import XPoster
from grok_install.safety.scanner import ApprovalDenied, RuntimeSafetyGate


def test_parse_github_url_https() -> None:
    t = parse_github_url("https://github.com/agentmindcloud/grok-install-cli")
    assert t.owner == "agentmindcloud"
    assert t.repo == "grok-install-cli"
    assert t.slug == "agentmindcloud/grok-install-cli"


def test_parse_github_url_shorthand() -> None:
    t = parse_github_url("github:agentmindcloud/grok-install-cli")
    assert t.clone_url.endswith(".git")


def test_parse_github_url_rejects_non_github() -> None:
    with pytest.raises(ValueError):
        parse_github_url("https://gitlab.com/x/y")


def test_fetch_repo_uses_runner(tmp_path: Path) -> None:
    calls = []

    def fake_run(args, check):  # noqa: ANN001
        calls.append(args)
        (tmp_path / "grok-install-cli").mkdir()

    # Route into a subdir so mkdir from fetch_repo doesn't collide.
    dest = tmp_path / "dest"
    fetch_repo(
        "https://github.com/agentmindcloud/grok-install-cli",
        dest,
        runner=lambda args, check=True: fake_run(args, check),
    )
    assert calls and calls[0][0] == "git"


def test_x_poster_requires_approval(valid_config) -> None:
    gate = RuntimeSafetyGate.from_config(valid_config)
    poster = XPoster(bearer_token="t", gate=gate)
    with pytest.raises(ApprovalDenied):
        poster.post_thread(["hello"])


def test_x_poster_posts_when_approved(valid_config) -> None:
    gate = RuntimeSafetyGate.from_config(valid_config, auto_approve=True)
    poster = XPoster(bearer_token="t", gate=gate)
    ids = poster.post_thread(["hello", "world"])
    assert len(ids) == 2
