"""Thin wrapper around the official xAI SDK.

Keeping the wrapper thin means ``grok-install`` plays nicely with whatever
version of ``xai-sdk`` the user installs. We import lazily so that unit tests
run without the SDK being present.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from grok_install.core.models import LLMConfig


class _SupportsChat(Protocol):
    def chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        parallel_tool_calls: bool = True,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> dict[str, Any]: ...


@dataclass
class ChatResponse:
    """Normalised shape returned from a chat completion."""

    content: str | None
    tool_calls: list[dict[str, Any]]
    raw: dict[str, Any]

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> ChatResponse:
        choice = (raw.get("choices") or [{}])[0]
        message = choice.get("message", {})
        return cls(
            content=message.get("content"),
            tool_calls=list(message.get("tool_calls") or []),
            raw=raw,
        )


class GrokClient:
    """Client facade. Works with the real xai-sdk and a test transport."""

    def __init__(
        self,
        llm: LLMConfig,
        *,
        transport: _SupportsChat | None = None,
        api_key: str | None = None,
    ) -> None:
        self._llm = llm
        self._transport = transport
        self._api_key = api_key

    @classmethod
    def from_config(
        cls,
        llm: LLMConfig,
        *,
        transport: _SupportsChat | None = None,
    ) -> GrokClient:
        if transport is None:
            api_key = os.environ.get(llm.api_key_env)
            if not api_key:
                raise RuntimeError(
                    f"env var {llm.api_key_env} is not set; cannot build Grok client"
                )
            transport = _build_default_transport(llm, api_key)
            return cls(llm, transport=transport, api_key=api_key)
        return cls(llm, transport=transport)

    @property
    def llm(self) -> LLMConfig:
        return self._llm

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        parallel_tool_calls: bool = True,
    ) -> ChatResponse:
        if self._transport is None:  # pragma: no cover - defensive
            raise RuntimeError("GrokClient has no transport configured")
        raw = self._transport.chat_completion(
            model=self._llm.model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
            temperature=self._llm.temperature,
            max_tokens=self._llm.max_tokens,
        )
        return ChatResponse.from_raw(raw)


def _build_default_transport(llm: LLMConfig, api_key: str) -> _SupportsChat:
    """Import xai-sdk lazily and wrap it in a ``_SupportsChat``-shaped adapter."""

    try:  # pragma: no cover - depends on optional dep
        from xai_sdk import Client as _XAIClient  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "xai-sdk not installed. Run: pip install 'grok-install[xai]'"
        ) from e

    sdk_client = _XAIClient(api_key=api_key, base_url=llm.base_url)  # type: ignore[call-arg]

    class _Adapter:  # pragma: no cover - thin passthrough
        def chat_completion(
            self,
            *,
            model: str,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            tool_choice: str | dict[str, Any] | None = None,
            parallel_tool_calls: bool = True,
            temperature: float = 0.7,
            max_tokens: int | None = None,
        ) -> dict[str, Any]:
            resp = sdk_client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                parallel_tool_calls=parallel_tool_calls,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp if isinstance(resp, dict) else resp.model_dump()

    return _Adapter()
