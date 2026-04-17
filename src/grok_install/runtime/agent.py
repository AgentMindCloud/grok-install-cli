"""Single-agent runner that drives the xAI SDK tool-calling loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from grok_install.core.models import AgentDefinition, GrokInstallConfig
from grok_install.runtime.client import ChatResponse, GrokClient
from grok_install.runtime.memory import MemoryStore
from grok_install.runtime.tools import ToolExecutor


@dataclass
class AgentRunResult:
    """Return shape for ``AgentRunner.run``."""

    output: str
    messages: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    handoff_to: str | None = None
    turns: int = 0


def _default_system_prompt(config: GrokInstallConfig, agent: AgentDefinition) -> str:
    lines = [
        f"You are {config.name!r}, a Grok-powered agent.",
        agent.description,
    ]
    if agent.handoff:
        lines.append(
            "If the user's need falls outside your scope, hand off to one of: "
            + ", ".join(agent.handoff)
            + " by calling the special tool 'handoff_to'."
        )
    lines.append(f"Safety profile: {config.safety.safety_profile}.")
    return "\n".join(lines)


def _handoff_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "handoff_to",
            "description": "Hand the conversation off to a named agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["agent"],
            },
        },
    }


class AgentRunner:
    """Runs one agent end-to-end, including the tool-calling loop."""

    def __init__(
        self,
        config: GrokInstallConfig,
        agent_name: str,
        *,
        client: GrokClient,
        executor: ToolExecutor,
        memory: MemoryStore | None = None,
    ) -> None:
        if agent_name not in config.agents:
            raise KeyError(f"no agent named {agent_name!r} in config")
        self._config = config
        self._agent_name = agent_name
        self._agent = config.agents[agent_name]
        self._client = client
        self._executor = executor
        self._memory = memory

    @property
    def name(self) -> str:
        return self._agent_name

    @property
    def agent(self) -> AgentDefinition:
        return self._agent

    def build_messages(self, user_input: str) -> list[dict[str, Any]]:
        system = self._agent.system_prompt or _default_system_prompt(
            self._config, self._agent
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user_input},
        ]

    def build_tools(self) -> list[dict[str, Any]]:
        tools = self._executor.registry.xai_tools(self._agent.tools)
        if self._agent.handoff:
            tools.append(_handoff_tool())
        return tools

    def run(self, user_input: str) -> AgentRunResult:
        messages = self.build_messages(user_input)
        tools = self.build_tools() or None
        max_turns = min(
            self._agent.max_turns_per_session,
            self._config.intelligence.max_turns_per_session,
        )
        all_tool_calls: list[dict[str, Any]] = []

        for turn in range(1, max_turns + 1):
            response = self._client.chat(
                messages,
                tools=tools,
                parallel_tool_calls=self._config.intelligence.parallel_tool_calls,
            )
            assistant_msg = _assistant_message(response)
            messages.append(assistant_msg)

            if not response.tool_calls:
                return AgentRunResult(
                    output=response.content or "",
                    messages=messages,
                    tool_calls=all_tool_calls,
                    turns=turn,
                )

            handoff = self._scan_for_handoff(response.tool_calls)
            if handoff:
                return AgentRunResult(
                    output=response.content or "",
                    messages=messages,
                    tool_calls=all_tool_calls,
                    handoff_to=handoff,
                    turns=turn,
                )

            for call in response.tool_calls:
                all_tool_calls.append(call)
                name = _tool_call_name(call)
                args = _tool_call_arguments(call)
                try:
                    result = self._executor.execute(name, args)
                except Exception as e:  # noqa: BLE001
                    result = f'{{"status":"error","error":{_json_escape(str(e))!s}}}'
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", name),
                        "name": name,
                        "content": result,
                    }
                )

        return AgentRunResult(
            output="(max turns reached without a final message)",
            messages=messages,
            tool_calls=all_tool_calls,
            turns=max_turns,
        )

    def _scan_for_handoff(self, tool_calls: list[dict[str, Any]]) -> str | None:
        for call in tool_calls:
            if _tool_call_name(call) != "handoff_to":
                continue
            args = _tool_call_arguments(call)
            if isinstance(args, str):
                import json

                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    continue
            target = args.get("agent") if isinstance(args, dict) else None
            if target and target in self._agent.handoff:
                return target
        return None


def _assistant_message(response: ChatResponse) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": response.content,
        "tool_calls": response.tool_calls or None,
    }


def _tool_call_name(call: dict[str, Any]) -> str:
    fn = call.get("function") or {}
    return fn.get("name") or call.get("name") or ""


def _tool_call_arguments(call: dict[str, Any]) -> str | dict[str, Any]:
    fn = call.get("function") or {}
    return fn.get("arguments") or call.get("arguments") or {}


def _json_escape(s: str) -> str:
    import json

    return json.dumps(s)
