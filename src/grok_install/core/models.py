"""Pydantic v2 models for grok-install.yaml v2.12 spec.

Every model uses ``extra="forbid"`` so typos are caught early. Field validators
emit clear error messages pointing to the offending value.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SafetyProfile = Literal["strict", "balanced", "research"]
MemoryScope = Literal["session", "long_term", "none"]
DeployTarget = Literal["vercel", "railway", "docker", "replit", "fly"]

_ENV_VAR_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
_AGENT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


class _Strict(BaseModel):
    """Base class enforcing strict, forbid-extra parsing for every subclass."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LLMConfig(_Strict):
    """Which Grok (or compatible) model to call and where to find the key."""

    provider: Literal["xai", "openai-compatible"] = "xai"
    model: str = Field(..., description="Model id, e.g. grok-2-latest")
    api_key_env: str = Field(
        ...,
        description="Name of env var that holds the API key (must end in _KEY or _ENV).",
    )
    base_url: str | None = Field(
        default=None,
        description="Override base URL for OpenAI-compatible providers.",
    )
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=200_000)

    @field_validator("api_key_env")
    @classmethod
    def _check_env_name(cls, v: str) -> str:
        if not _ENV_VAR_PATTERN.match(v):
            raise ValueError(
                f"api_key_env must be UPPER_SNAKE_CASE, got {v!r}"
            )
        if not (v.endswith("_KEY") or v.endswith("_ENV") or v.endswith("_TOKEN")):
            raise ValueError(
                f"api_key_env must end in _KEY, _ENV, or _TOKEN; got {v!r}"
            )
        return v

    @field_validator("model")
    @classmethod
    def _check_model(cls, v: str) -> str:
        if not v or " " in v:
            raise ValueError(f"model id cannot be empty or contain spaces; got {v!r}")
        return v


class IntelligenceLayer(_Strict):
    """Opt-in runtime capabilities."""

    function_calling: bool = True
    parallel_tool_calls: bool = True
    real_time_tools: bool = False
    multi_agent_swarm: bool = False
    structured_outputs: bool = False
    max_turns_per_session: int = Field(default=20, ge=1, le=1000)


class XNativeRuntime(_Strict):
    """Runtime surface — where the agent actually runs."""

    type: Literal["cli", "x-bot", "webhook", "scheduled", "http"] = "cli"
    permissions: list[str] = Field(default_factory=list)
    grok_orchestrator: bool = False
    schedule: str | None = Field(
        default=None,
        description="Cron expression for scheduled agents.",
    )

    @field_validator("permissions")
    @classmethod
    def _check_permissions(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        for p in v:
            if not p.strip():
                raise ValueError("permission entries cannot be blank")
            if p in seen:
                raise ValueError(f"duplicate permission {p!r}")
            seen.add(p)
        return v


class RateLimit(_Strict):
    """Simple rate-limit declaration used by X-writing tools."""

    per: Literal["minute", "hour", "day"] = "hour"
    max: int = Field(..., ge=1)


class SafetyConfig(_Strict):
    """How strictly to scan & gate this agent."""

    pre_install_scan: bool = True
    verified_by_grok: bool = False
    minimum_keys_only: bool = True
    safety_profile: SafetyProfile = "balanced"
    blocked_tools: list[str] = Field(default_factory=list)
    rate_limits: dict[str, RateLimit] = Field(default_factory=dict)
    require_human_approval: list[str] = Field(
        default_factory=lambda: ["post_thread", "reply_to_mention", "post_image"],
        description="Tool names that must block until the user confirms.",
    )


class PromotionConfig(_Strict):
    """Optional social-promotion toggles (all default off)."""

    auto_welcome: bool = False
    auto_share: bool = False
    weekly_highlight: bool = False


class VoiceConfig(_Strict):
    """Voice capability — STT, TTS, microphone, speaker.

    Defaults keep voice entirely off. Enabling it unlocks a new scanner surface
    (``safety/scanner._scan_voice``) that checks for unbounded recording,
    voice + write permission combos, and misconfigured audio permissions.
    """

    enabled: bool = False
    stt_provider: Literal["xai", "whisper", "deepgram", "none"] = "none"
    tts_provider: Literal["xai", "elevenlabs", "openai", "none"] = "none"
    record_audio: bool = False
    max_recording_seconds: int | None = Field(default=None, ge=1, le=3600)
    store_recordings: bool = False
    wake_word: str | None = None

    @field_validator("wake_word")
    @classmethod
    def _check_wake_word(cls, v: str | None) -> str | None:
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("wake_word cannot be blank if set")
        if len(stripped) > 64:
            raise ValueError("wake_word must be 64 chars or fewer")
        return stripped


class ToolParameterSchema(_Strict):
    """Minimal JSON-Schema subset used to describe a tool parameter."""

    type: Literal["object", "string", "number", "integer", "boolean", "array"]
    properties: dict[str, dict[str, Any]] | None = None
    items: dict[str, Any] | None = None
    required: list[str] | None = None
    description: str | None = None
    enum: list[Any] | None = None

    @model_validator(mode="after")
    def _object_requires_properties(self) -> ToolParameterSchema:
        if self.type == "object" and self.properties is None:
            raise ValueError("tool parameters of type 'object' must declare properties")
        return self


class ToolSchema(_Strict):
    """A tool the agent may call."""

    name: str = Field(..., description="Snake_case name used in function calls.")
    description: str = Field(..., min_length=1, max_length=1024)
    parameters: ToolParameterSchema = Field(
        ...,
        description="JSON-Schema object describing the tool's input.",
    )
    required: list[str] = Field(default_factory=list)
    permission: str | None = Field(
        default=None,
        description="Permission name that must be present in runtime.permissions.",
    )
    rate_limit: RateLimit | None = None

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]{0,63}$", v):
            raise ValueError(
                f"tool name must be snake_case, 1-64 chars, got {v!r}"
            )
        return v

    def to_xai_tool(self) -> dict[str, Any]:
        """Render the schema in xAI/OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters.model_dump(exclude_none=True),
            },
        }


class AgentDefinition(_Strict):
    """A named agent. Multiple agents enable swarm orchestration."""

    description: str = Field(..., min_length=1, max_length=2048)
    system_prompt: str | None = None
    tools: list[str] = Field(
        default_factory=list,
        description="Tool names — resolved against builtins or the tools block.",
    )
    memory: MemoryScope = "session"
    max_turns_per_session: int = Field(default=20, ge=1, le=1000)
    handoff: list[str] = Field(
        default_factory=list,
        description="Names of agents this agent may hand off to.",
    )

    @field_validator("tools", "handoff")
    @classmethod
    def _check_unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("list must not contain duplicates")
        return v


class GrokInstallConfig(_Strict):
    """Root of every grok-install.yaml file (spec v2.12)."""

    spec_version: str = Field(default="2.12", pattern=r"^\d+\.\d+(\.\d+)?$")
    name: str = Field(..., description="Agent/project slug.")
    version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+([.\-+].+)?$")
    summary: str | None = None
    authors: list[str] = Field(default_factory=list)
    license: str = "Apache-2.0"
    llm: LLMConfig
    intelligence: IntelligenceLayer = Field(default_factory=IntelligenceLayer)
    runtime: XNativeRuntime = Field(default_factory=XNativeRuntime)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    promotion: PromotionConfig = Field(default_factory=PromotionConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    tools: list[ToolSchema] = Field(default_factory=list)
    agents: dict[str, AgentDefinition] = Field(default_factory=dict)
    deploy_targets: list[DeployTarget] = Field(default_factory=list)
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Non-secret default env var values. Never put secrets here.",
    )

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if not _AGENT_NAME_PATTERN.match(v):
            raise ValueError(
                "name must be lowercase slug (a-z, 0-9, _ or -), 2-64 chars"
            )
        return v

    @field_validator("env")
    @classmethod
    def _check_env(cls, v: dict[str, str]) -> dict[str, str]:
        for key, value in v.items():
            if not _ENV_VAR_PATTERN.match(key):
                raise ValueError(f"env key {key!r} must be UPPER_SNAKE_CASE")
            lowered = value.lower()
            if any(s in lowered for s in ("sk-", "xai-", "ghp_", "bearer ")):
                raise ValueError(
                    f"env[{key}] looks like a secret — move it to your shell, "
                    "not the YAML"
                )
        return v

    @model_validator(mode="after")
    def _require_at_least_one_agent(self) -> GrokInstallConfig:
        if not self.agents:
            self.agents = {
                "default": AgentDefinition(
                    description=self.summary or f"{self.name} default agent"
                )
            }
        return self

    @model_validator(mode="after")
    def _handoff_targets_exist(self) -> GrokInstallConfig:
        names = set(self.agents)
        for agent_name, agent in self.agents.items():
            for target in agent.handoff:
                if target not in names:
                    raise ValueError(
                        f"agent {agent_name!r} hands off to unknown agent {target!r}"
                    )
                if target == agent_name:
                    raise ValueError(
                        f"agent {agent_name!r} cannot hand off to itself"
                    )
        return self

    @model_validator(mode="after")
    def _tool_names_unique(self) -> GrokInstallConfig:
        names = [t.name for t in self.tools]
        if len(set(names)) != len(names):
            raise ValueError("duplicate tool names in tools block")
        return self
