"""Build-order and reactive construction proposals."""

from sc2_ontology_agent.domain.intent import IntentType
from sc2_ontology_agent.policy.hierarchical.blackboard import StrategicBlackboard
from sc2_ontology_agent.policy.hierarchical.commands import (
    CandidateIntent,
    ProducerKind,
    ProductionGoal,
    TaskState,
)
from sc2_ontology_agent.policy.hierarchical.managers import _candidate

_BUILD_COSTS: dict[IntentType, tuple[int, int, ProducerKind | None]] = {
    IntentType.BUILD_SUPPLY: (100, 0, None),
    IntentType.BUILD_BARRACKS: (150, 0, None),
    IntentType.BUILD_REFINERY: (75, 0, None),
    IntentType.EXPAND_COMMAND_CENTER: (400, 0, None),
    IntentType.BUILD_TECHLAB: (50, 25, ProducerKind.ADDONLESS_BARRACKS),
    IntentType.BUILD_REACTOR: (50, 50, ProducerKind.ADDONLESS_BARRACKS),
}


class ConstructionManager:
    """Preserve build-order ownership while reacting to supply pressure."""

    def propose(self, board: StrategicBlackboard) -> list[CandidateIntent]:
        candidates: list[CandidateIntent] = []
        current = _current_goal(board)
        supply_pressure = board.snapshot.supply_left <= board.config.supply_buffer
        expansion_waiting_for_workers = (
            current is not None
            and current.intent_type is IntentType.EXPAND_COMMAND_CENTER
            and board.snapshot.worker_count < board.config.expansion_worker_threshold
        )
        if (
            current is not None
            and current.intent_type in _BUILD_COSTS
            and not expansion_waiting_for_workers
        ):
            candidates.append(
                self._goal_candidate(
                    board,
                    current,
                    priority=(
                        90
                        if supply_pressure and current.intent_type is IntentType.BUILD_SUPPLY
                        else 70
                    ),
                )
            )

        snapshot = board.snapshot
        if (
            supply_pressure
            and IntentType.BUILD_SUPPLY.value not in snapshot.pending_actions
            and (current is None or current.intent_type is not IntentType.BUILD_SUPPLY)
        ):
            candidates.append(
                _candidate(
                    board,
                    IntentType.BUILD_SUPPLY,
                    90,
                    "supply_buffer_reached",
                    f"build:reactive_supply:{snapshot.game_loop}",
                    "construction",
                    mineral_cost=100,
                    uses_build_worker=True,
                )
            )
        return candidates

    @staticmethod
    def _goal_candidate(
        board: StrategicBlackboard,
        goal: ProductionGoal,
        *,
        priority: int,
    ) -> CandidateIntent:
        mineral_cost, vespene_cost, producer = _BUILD_COSTS[goal.intent_type]
        return _candidate(
            board,
            goal.intent_type,
            priority,
            "next_build_order_goal",
            goal.key,
            "construction",
            mineral_cost=mineral_cost,
            vespene_cost=vespene_cost,
            uses_build_worker=producer is None,
            producer=producer,
        )


def _current_goal(board: StrategicBlackboard) -> ProductionGoal | None:
    return next(
        (
            goal
            for goal in board.production_goals
            if board.tasks[goal.key].state is not TaskState.COMPLETED
        ),
        None,
    )
