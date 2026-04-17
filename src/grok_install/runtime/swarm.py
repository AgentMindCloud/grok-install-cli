"""Multi-agent swarm orchestrator with explicit hand-off."""

from __future__ import annotations

from dataclasses import dataclass, field

from grok_install.core.models import GrokInstallConfig
from grok_install.runtime.agent import AgentRunner, AgentRunResult


@dataclass
class SwarmTrace:
    """What each agent said, in order."""

    hops: list[tuple[str, AgentRunResult]] = field(default_factory=list)

    @property
    def final_output(self) -> str:
        return self.hops[-1][1].output if self.hops else ""


class SwarmOrchestrator:
    """Drive multi-agent hand-offs. Guards against runaway cycles."""

    def __init__(
        self,
        config: GrokInstallConfig,
        runners: dict[str, AgentRunner],
        *,
        max_hops: int = 8,
    ) -> None:
        if not config.intelligence.multi_agent_swarm:
            raise RuntimeError(
                "SwarmOrchestrator requires intelligence.multi_agent_swarm: true"
            )
        self._config = config
        self._runners = runners
        self._max_hops = max_hops

    @property
    def agent_names(self) -> list[str]:
        return list(self._runners)

    def run(self, user_input: str, start: str | None = None) -> SwarmTrace:
        start_name = start or next(iter(self._runners))
        if start_name not in self._runners:
            raise KeyError(f"no agent named {start_name!r}")
        trace = SwarmTrace()
        visited: list[str] = []
        current = start_name
        message = user_input

        for _ in range(self._max_hops):
            visited.append(current)
            runner = self._runners[current]
            result = runner.run(message)
            trace.hops.append((current, result))
            if not result.handoff_to:
                return trace
            if result.handoff_to in visited:
                trace.hops.append(
                    (
                        current,
                        AgentRunResult(
                            output=(
                                f"(cycle guard: refused hand-off back to "
                                f"{result.handoff_to!r})"
                            ),
                            messages=[],
                        ),
                    )
                )
                return trace
            current = result.handoff_to
            message = result.output or user_input
        return trace
