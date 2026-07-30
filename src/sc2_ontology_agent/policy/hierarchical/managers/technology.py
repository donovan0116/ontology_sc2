"""Technology and townhall upgrade proposals."""

from sc2_ontology_agent.domain.intent import IntentType
from sc2_ontology_agent.policy.hierarchical.blackboard import StrategicBlackboard
from sc2_ontology_agent.policy.hierarchical.commands import (
    CandidateIntent,
    ProducerKind,
    ProductionGoal,
    TaskState,
)
from sc2_ontology_agent.policy.hierarchical.managers import _candidate

_TECH_COSTS: dict[IntentType, tuple[int, int, ProducerKind]] = {
    IntentType.UPGRADE_ORBITAL: (150, 0, ProducerKind.TOWNHALL),
    IntentType.RESEARCH_STIM: (100, 100, ProducerKind.TECHLAB),
}


class TechnologyManager:
    """Own ordered Orbital and Stim milestones."""

    def propose(self, board: StrategicBlackboard) -> list[CandidateIntent]:
        current = _current_goal(board)
        if current is None or current.intent_type not in _TECH_COSTS:
            return []
        if current.intent_type is IntentType.RESEARCH_STIM and board.snapshot.stim_pending:
            return []

        mineral_cost, vespene_cost, producer = _TECH_COSTS[current.intent_type]
        return [
            _candidate(
                board,
                current.intent_type,
                70,
                "next_technology_goal",
                current.key,
                "technology",
                mineral_cost=mineral_cost,
                vespene_cost=vespene_cost,
                producer=producer,
            )
        ]


def _current_goal(board: StrategicBlackboard) -> ProductionGoal | None:
    return next(
        (
            goal
            for goal in board.production_goals
            if board.tasks[goal.key].state is not TaskState.COMPLETED
        ),
        None,
    )
