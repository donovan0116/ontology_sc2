"""One-shot scouting proposals."""

from sc2_ontology_agent.domain.intent import IntentType
from sc2_ontology_agent.policy.hierarchical.blackboard import StrategicBlackboard
from sc2_ontology_agent.policy.hierarchical.commands import (
    CandidateIntent,
    ProductionGoal,
)
from sc2_ontology_agent.policy.hierarchical.managers import _candidate

_SCOUT_GOAL = ProductionGoal(
    "scout:enemy_start",
    IntentType.SCOUT_ENEMY_START,
    None,
    True,
    required=False,
)


class ScoutManager:
    """Request the opening scout once its configured window begins."""

    def propose(self, board: StrategicBlackboard) -> list[CandidateIntent]:
        snapshot = board.snapshot
        board.ensure_task(
            _SCOUT_GOAL,
            include_in_production_queue=False,
        )
        if (
            board.scout_accepted
            or snapshot.game_time_seconds < board.config.scout_start_time_seconds
        ):
            return []
        return [
            _candidate(
                board,
                IntentType.SCOUT_ENEMY_START,
                50,
                "scout_time_window_open",
                "scout:enemy_start",
                "scout",
                uses_worker=True,
            )
        ]
