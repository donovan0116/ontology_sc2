from typing import Protocol, runtime_checkable

from sc2_ontology_agent.domain.intent import MacroIntent
from sc2_ontology_agent.domain.records import ExecutionResult, StrategyEvent
from sc2_ontology_agent.domain.state import GameSnapshot


class TacticalAdvisor(Protocol):
    """Replaceable high-level recommendation boundary."""

    def recommend(self, snapshot: GameSnapshot) -> list[MacroIntent]: ...


@runtime_checkable
class ExecutionAwareAdvisor(Protocol):
    """Advisor that consumes command-translation outcomes."""

    def observe_execution(
        self,
        intent: MacroIntent,
        result: ExecutionResult,
    ) -> None: ...


@runtime_checkable
class TraceableAdvisor(Protocol):
    """Advisor that exposes buffered strategy events."""

    def drain_events(self) -> tuple[StrategyEvent, ...]: ...
