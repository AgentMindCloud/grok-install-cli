"""Parser + Pydantic model tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from grok_install.core.models import GrokInstallConfig, LLMConfig, ToolParameterSchema, ToolSchema
from grok_install.core.parser import ParseError, load_config, parse_config


def test_load_valid_config(fixtures_dir: Path) -> None:
    config = load_config(fixtures_dir / "valid.yaml")
    assert isinstance(config, GrokInstallConfig)
    assert config.name == "valid-sample"
    assert config.llm.model == "grok-2-latest"
    assert "default" in config.agents


def test_load_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ParseError):
        load_config(tmp_path)


def test_llm_api_key_env_must_be_snake(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        LLMConfig(model="grok-2-latest", api_key_env="xaiKey")


def test_llm_api_key_env_must_end_in_known_suffix() -> None:
    with pytest.raises(ValueError):
        LLMConfig(model="grok-2-latest", api_key_env="XAI_SOMETHING")


def test_name_must_be_slug() -> None:
    with pytest.raises(ValueError):
        GrokInstallConfig(
            name="Bad Name",
            llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        )


def test_env_rejects_secret_prefix() -> None:
    with pytest.raises(ValueError):
        GrokInstallConfig(
            name="demo",
            llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
            env={"XAI_API_KEY": "xai-abcdefabcdefabcdefabcdefabcdef1234"},
        )


def test_duplicate_tool_name_rejected() -> None:
    params = ToolParameterSchema(
        type="object", properties={"x": {"type": "string"}}, required=["x"]
    )
    with pytest.raises(ValueError):
        GrokInstallConfig(
            name="demo",
            llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
            tools=[
                ToolSchema(name="read_file", description="a", parameters=params),
                ToolSchema(name="read_file", description="b", parameters=params),
            ],
        )


def test_handoff_cycle_to_self_rejected() -> None:
    from grok_install.core.models import AgentDefinition

    with pytest.raises(ValueError):
        GrokInstallConfig(
            name="demo",
            llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
            agents={
                "a": AgentDefinition(description="x", handoff=["a"]),
            },
        )


def test_handoff_to_missing_agent_rejected() -> None:
    from grok_install.core.models import AgentDefinition

    with pytest.raises(ValueError):
        GrokInstallConfig(
            name="demo",
            llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
            agents={
                "a": AgentDefinition(description="x", handoff=["nonexistent"]),
            },
        )


def test_object_schema_requires_properties() -> None:
    with pytest.raises(ValueError):
        ToolParameterSchema(type="object")


def test_parser_recognizes_grok_swarm_filename(
    tmp_path: Path, fixtures_dir: Path
) -> None:
    (tmp_path / "grok-swarm.yaml").write_text(
        (fixtures_dir / "swarm.yaml").read_text(), encoding="utf-8"
    )
    config = load_config(tmp_path)
    assert config.name == "swarm-sample"


def test_parser_recognizes_grok_voice_filename(
    tmp_path: Path, fixtures_dir: Path
) -> None:
    (tmp_path / "grok-voice.yaml").write_text(
        (fixtures_dir / "valid.yaml").read_text(), encoding="utf-8"
    )
    config = load_config(tmp_path)
    assert config.name == "valid-sample"


def test_optional_swarm_and_voice_top_level_keys(tmp_path: Path) -> None:
    path = tmp_path / "grok-install.yaml"
    path.write_text(
        'spec_version: "2.12"\n'
        "name: has-swarm-voice\n"
        "llm:\n"
        "  model: grok-2-latest\n"
        "  api_key_env: XAI_API_KEY\n"
        "swarm:\n"
        "  enabled: true\n"
        "  topology: star\n"
        "  max_agents: 4\n"
        "voice:\n"
        "  enabled: true\n"
        "  provider: xai-voice\n"
        "  language: en-US\n",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.swarm is not None
    assert config.swarm.enabled is True
    assert config.swarm.topology == "star"
    assert config.voice is not None
    assert config.voice.provider == "xai-voice"


def test_overlay_merging(tmp_path: Path, fixtures_dir: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "grok-install.yaml").write_text(
        (fixtures_dir / "valid.yaml").read_text()
    )
    overlay = project / ".grok"
    overlay.mkdir()
    (overlay / "override.yaml").write_text(
        "llm:\n  temperature: 0.1\n", encoding="utf-8"
    )
    config = load_config(project)
    assert config.llm.temperature == pytest.approx(0.1)


def test_line_numbers_in_errors(tmp_path: Path) -> None:
    path = tmp_path / "grok-install.yaml"
    path.write_text(
        "name: bad space\n"
        "llm:\n"
        "  model: grok-2-latest\n"
        "  api_key_env: XAI_API_KEY\n",
        encoding="utf-8",
    )
    with pytest.raises(ParseError) as excinfo:
        load_config(path)
    assert "line" in str(excinfo.value) or "name" in str(excinfo.value)


def test_parse_empty_dict_fails() -> None:
    with pytest.raises(ParseError):
        parse_config({})


def test_to_xai_tool_shape() -> None:
    params = ToolParameterSchema(
        type="object", properties={"q": {"type": "string"}}, required=["q"]
    )
    schema = ToolSchema(name="search_x", description="search", parameters=params)
    rendered = schema.to_xai_tool()
    assert rendered["type"] == "function"
    assert rendered["function"]["name"] == "search_x"
    assert rendered["function"]["parameters"]["type"] == "object"
