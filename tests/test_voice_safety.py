"""Voice-specific safety scanner tests."""

from __future__ import annotations

from pathlib import Path

from grok_install.core.models import (
    AgentDefinition,
    GrokInstallConfig,
    LLMConfig,
    SafetyConfig,
    ToolParameterSchema,
    ToolSchema,
    VoiceConfig,
    XNativeRuntime,
)
from grok_install.core.parser import load_config
from grok_install.safety.scanner import scan_config, scan_path


def _obj_schema() -> ToolParameterSchema:
    return ToolParameterSchema(type="object", properties={})


def test_voice_fixture_scans_clean(fixtures_dir: Path) -> None:
    report = scan_path(fixtures_dir / "voice.yaml")
    assert report.ok, [f.code for f in report.reds]


def test_voice_bad_fixture_flags_unbounded_recording(fixtures_dir: Path) -> None:
    report = scan_path(fixtures_dir / "voice_bad.yaml")
    assert not report.ok
    assert any(f.code == "voice-unbounded-recording" for f in report.reds)


def test_default_voice_adds_no_findings(fixtures_dir: Path) -> None:
    config = load_config(fixtures_dir / "valid.yaml")
    assert config.voice.enabled is False
    report = scan_config(config)
    voice_codes = {
        "voice-unbounded-recording",
        "voice-research-write-combo",
        "voice-wake-write-without-approval",
        "voice-long-recording",
        "voice-store-loose-profile",
        "voice-missing-audio-perm",
        "voice-perm-without-enable",
    }
    assert not any(f.code in voice_codes for f in report.findings)


def test_audio_permission_without_voice_enabled_is_red() -> None:
    config = GrokInstallConfig(
        name="dead-audio",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        runtime=XNativeRuntime(permissions=["audio.read"]),
        agents={"default": AgentDefinition(description="x")},
    )
    report = scan_config(config)
    assert any(f.code == "voice-perm-without-enable" for f in report.reds)


def test_voice_research_with_write_is_red() -> None:
    config = GrokInstallConfig(
        name="voice-research",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        runtime=XNativeRuntime(permissions=["audio.read", "x.write"]),
        safety=SafetyConfig(safety_profile="research"),
        voice=VoiceConfig(enabled=True),
        agents={"default": AgentDefinition(description="x")},
    )
    report = scan_config(config)
    assert any(f.code == "voice-research-write-combo" for f in report.reds)


def test_wake_word_without_approval_gate_is_red() -> None:
    config = GrokInstallConfig(
        name="wake",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        runtime=XNativeRuntime(permissions=["audio.read"]),
        safety=SafetyConfig(
            safety_profile="strict", require_human_approval=["post_thread"]
        ),
        voice=VoiceConfig(enabled=True, wake_word="hey grok"),
        tools=[
            ToolSchema(
                name="tweet",
                description="send tweet",
                parameters=_obj_schema(),
                permission="x.write",
            ),
        ],
        agents={"default": AgentDefinition(description="x", tools=["tweet"])},
    )
    report = scan_config(config)
    assert any(f.code == "voice-wake-write-without-approval" for f in report.reds)


def test_long_recording_yellow() -> None:
    config = GrokInstallConfig(
        name="long-rec",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        runtime=XNativeRuntime(permissions=["audio.read", "audio.record"]),
        safety=SafetyConfig(safety_profile="strict"),
        voice=VoiceConfig(
            enabled=True, record_audio=True, max_recording_seconds=3000
        ),
        agents={"default": AgentDefinition(description="x")},
    )
    report = scan_config(config)
    assert any(f.code == "voice-long-recording" for f in report.yellows)


def test_store_recordings_loose_profile_yellow() -> None:
    config = GrokInstallConfig(
        name="store-rec",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        runtime=XNativeRuntime(permissions=["audio.read"]),
        safety=SafetyConfig(safety_profile="balanced"),
        voice=VoiceConfig(
            enabled=True,
            record_audio=True,
            max_recording_seconds=30,
            store_recordings=True,
        ),
        agents={"default": AgentDefinition(description="x")},
    )
    report = scan_config(config)
    assert any(f.code == "voice-store-loose-profile" for f in report.yellows)


def test_voice_enabled_without_audio_perm_yellow() -> None:
    config = GrokInstallConfig(
        name="no-audio-perm",
        llm=LLMConfig(model="grok-2-latest", api_key_env="XAI_API_KEY"),
        runtime=XNativeRuntime(permissions=["fs.read"]),
        safety=SafetyConfig(safety_profile="strict"),
        voice=VoiceConfig(enabled=True),
        agents={"default": AgentDefinition(description="x")},
    )
    report = scan_config(config)
    assert any(f.code == "voice-missing-audio-perm" for f in report.yellows)
