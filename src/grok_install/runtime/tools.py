"""Tool registry + executor used at runtime.

Resolution rules:
1. YAML tool block wins (lets users override a builtin).
2. Fall back to the built-in registry.
3. Unknown name → hard error before we call the model.

Execution rules:
- Every tool call is passed through the safety scanner.
- Tools listed in ``require_human_approval`` block until the user confirms.
- Rate limits are enforced per-process via an in-memory bucket.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable

from grok_install.core.models import GrokInstallConfig, RateLimit, ToolSchema
from grok_install.core.registry import BLOCKED_TOOL_NAMES, get_builtin_tool
from grok_install.safety.scanner import RuntimeSafetyGate

ToolHandler = Callable[[dict[str, Any]], Any]


class ToolNotFound(KeyError):
    """Raised when the model asks for a tool that wasn't declared."""


class ToolBlocked(PermissionError):
    """Raised when a tool call is denied by safety or by the user."""


class RateLimitExceeded(RuntimeError):
    """Raised when a tool's declared rate limit would be exceeded."""


@dataclass
class ToolRegistry:
    """Resolves tool names to schemas + handlers."""

    schemas: dict[str, ToolSchema] = field(default_factory=dict)
    handlers: dict[str, ToolHandler] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: GrokInstallConfig) -> ToolRegistry:
        reg = cls()
        for tool in config.tools:
            reg.schemas[tool.name] = tool
        for agent in config.agents.values():
            for name in agent.tools:
                if name in reg.schemas:
                    continue
                builtin = get_builtin_tool(name)
                if builtin is None:
                    raise ToolNotFound(
                        f"tool {name!r} is neither a builtin nor declared under tools:"
                    )
                reg.schemas[name] = builtin
        for blocked in BLOCKED_TOOL_NAMES & set(reg.schemas):
            raise ToolBlocked(
                f"tool {blocked!r} is on the hard block list and cannot be used"
            )
        for blocked in config.safety.blocked_tools:
            reg.schemas.pop(blocked, None)
        return reg

    def register_handler(self, name: str, handler: ToolHandler) -> None:
        if name not in self.schemas:
            raise ToolNotFound(f"cannot handle unknown tool {name!r}")
        self.handlers[name] = handler

    def xai_tools(self, allowed: list[str] | None = None) -> list[dict[str, Any]]:
        names = allowed if allowed is not None else list(self.schemas)
        return [self.schemas[n].to_xai_tool() for n in names if n in self.schemas]


class _RateLimiter:
    """Simple sliding-window limiter keyed by tool name."""

    _WINDOWS = {"minute": 60.0, "hour": 3600.0, "day": 86_400.0}

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, name: str, limit: RateLimit) -> None:
        window = self._WINDOWS[limit.per]
        bucket = self._events[name]
        now = time.time()
        while bucket and now - bucket[0] > window:
            bucket.popleft()
        if len(bucket) >= limit.max:
            raise RateLimitExceeded(
                f"rate limit for tool {name!r}: {limit.max} per {limit.per}"
            )
        bucket.append(now)


@dataclass
class ToolExecutor:
    """Executes tool calls for an agent under the safety gate."""

    registry: ToolRegistry
    gate: RuntimeSafetyGate
    rate_limiter: _RateLimiter = field(default_factory=_RateLimiter)

    def execute(self, name: str, arguments: str | dict[str, Any]) -> str:
        schema = self.registry.schemas.get(name)
        if schema is None:
            raise ToolNotFound(f"model called unknown tool {name!r}")

        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError as e:
                raise ToolBlocked(
                    f"tool {name!r} was called with invalid JSON arguments: {e}"
                ) from e
        else:
            parsed = dict(arguments)

        self.gate.check(name, parsed)

        if schema.rate_limit is not None:
            self.rate_limiter.check(name, schema.rate_limit)

        handler = self.registry.handlers.get(name)
        if handler is None:
            return json.dumps(
                {
                    "status": "dry-run",
                    "tool": name,
                    "note": "no handler registered; returning echo",
                    "arguments": parsed,
                }
            )
        try:
            result = handler(parsed)
        except Exception as e:  # noqa: BLE001 - surface to the model
            return json.dumps({"status": "error", "error": str(e)})
        return _serialise_result(result)


def _serialise_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except TypeError:
        return json.dumps(str(result))
