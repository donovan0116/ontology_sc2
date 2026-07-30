"""Focused proposal managers for the hierarchical macro policy."""

from collections.abc import Mapping
from typing import TypedDict, Unpack

from sc2_ontology_agent.domain.intent import IntentParameter, IntentType, MacroIntent
from sc2_ontology_agent.policy.hierarchical.blackboard import StrategicBlackboard
from sc2_ontology_agent.policy.hierarchical.commands import CandidateIntent, ProducerKind


class _CandidateCosts(TypedDict, total=False):
    mineral_cost: int
    vespene_cost: int
    supply_cost: float
    uses_build_worker: bool
    uses_worker: bool
    producer: ProducerKind | None
    emergency: bool


def _candidate(
    board: StrategicBlackboard,
    intent_type: IntentType,
    priority: int,
    reason: str,
    task_key: str,
    source_manager: str,
    *,
    parameters: Mapping[str, IntentParameter] | None = None,
    **costs: Unpack[_CandidateCosts],
) -> CandidateIntent:
    intent_parameters: dict[str, IntentParameter] = {}
    if parameters is not None:
        intent_parameters.update(parameters)
    intent_parameters["task_key"] = task_key
    intent_parameters["source_manager"] = source_manager
    intent = MacroIntent(
        intent_type,
        priority,
        reason,
        board.snapshot.game_loop,
        intent_parameters,
    )
    return CandidateIntent(intent=intent, task_key=task_key, **costs)
