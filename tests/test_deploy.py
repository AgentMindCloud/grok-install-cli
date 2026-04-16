"""Deploy generator tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from grok_install.core.models import GrokInstallConfig
from grok_install.deploy.base import get_generator, write_artifacts


@pytest.mark.parametrize("target", ["vercel", "railway", "docker", "replit"])
def test_generators_write_files(
    tmp_path: Path, valid_config: GrokInstallConfig, target: str
) -> None:
    gen = get_generator(target)
    arts = gen.artifacts(valid_config)
    result = write_artifacts(target, arts, tmp_path, instructions=gen.instructions(valid_config))
    assert all(p.exists() for p in result.written)
    assert result.instructions  # not empty


def test_unknown_target_rejected() -> None:
    with pytest.raises(KeyError):
        get_generator("fly-by-night")


def test_vercel_generates_api_entry(tmp_path: Path, valid_config: GrokInstallConfig) -> None:
    gen = get_generator("vercel")
    arts = gen.artifacts(valid_config)
    names = {a.path.name for a in arts}
    assert names == {"vercel.json", "index.py", "requirements.txt", ".env.example"}


def test_env_example_includes_api_key(valid_config: GrokInstallConfig) -> None:
    gen = get_generator("docker")
    arts = gen.artifacts(valid_config)
    env = next(a for a in arts if a.path.name == ".env.example")
    assert valid_config.llm.api_key_env in env.content


def test_write_skips_existing_without_force(
    tmp_path: Path, valid_config: GrokInstallConfig
) -> None:
    gen = get_generator("docker")
    arts = gen.artifacts(valid_config)
    arts[0] = type(arts[0])(path=arts[0].path, content=arts[0].content, overwrite=False)
    (tmp_path / arts[0].path).write_text("existing")
    result = write_artifacts("docker", arts, tmp_path, instructions="", force=False)
    assert (tmp_path / arts[0].path) in result.skipped
