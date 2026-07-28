"""Framework-independent domain values."""

from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.domain.records import ExecutionResult, ExecutionStatus
from sc2_ontology_agent.domain.state import GameSnapshot

__all__ = [
    "ExecutionResult",
    "ExecutionStatus",
    "GameSnapshot",
    "IntentType",
    "MacroIntent",
]
