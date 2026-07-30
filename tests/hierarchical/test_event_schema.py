from sc2_ontology_agent.config import BotConfig
from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.domain.records import ExecutionResult, ExecutionStatus
from sc2_ontology_agent.policy.hierarchical.advisor import HierarchicalRulePolicy
from sc2_ontology_agent.policy.hierarchical.blackboard import StrategicBlackboard
from sc2_ontology_agent.policy.hierarchical.combat_strategy import CombatStrategy
from sc2_ontology_agent.policy.hierarchical.commands import (
    CandidateIntent,
    ProductionGoal,
    ProductionPhase,
)
from sc2_ontology_agent.policy.hierarchical.production_strategy import ProductionStrategy
from sc2_ontology_agent.policy.hierarchical.scheduler import CommandScheduler

from .conftest import make_snapshot


def _candidate(
    intent_type: IntentType,
    priority: int,
    task_key: str,
    *,
    mineral_cost: int = 0,
) -> CandidateIntent:
    return CandidateIntent(
        MacroIntent(
            intent_type,
            priority,
            task_key,
            100,
            {"task_key": task_key, "source_manager": "test"},
        ),
        task_key,
        mineral_cost=mineral_cost,
    )


def test_hierarchical_events_have_documented_scalar_detail_schemas() -> None:
    board = StrategicBlackboard(BotConfig())
    board.update(
        make_snapshot(
            minerals=100,
            barracks_count=1,
            ready_barracks_count=1,
            refinery_count=1,
            ready_refinery_count=1,
            orbital_count=1,
        )
    )
    ProductionStrategy().update(board)
    board.production_phase = ProductionPhase.MUSTER
    CombatStrategy().update(board)

    goal = ProductionGoal(
        "event:task",
        IntentType.BUILD_SUPPLY,
        "supply_depot_count",
        99,
    )
    board.ensure_task(goal)
    CommandScheduler().select(
        board.snapshot,
        [
            _candidate(IntentType.BUILD_SUPPLY, 80, goal.key, mineral_cost=50),
            _candidate(IntentType.BUILD_REFINERY, 70, "event:suppressed", mineral_cost=100),
        ],
        board,
    )
    board.observe_execution(
        MacroIntent(
            IntentType.BUILD_SUPPLY,
            80,
            "event:task",
            board.snapshot.game_loop,
            {"task_key": goal.key, "source_manager": "test"},
        ),
        ExecutionResult(ExecutionStatus.ACCEPTED),
    )
    board.update(make_snapshot(game_time_seconds=131.0, supply_depot_count=0))

    advisor = HierarchicalRulePolicy(BotConfig())
    advisor.recommend(make_snapshot(minerals=500))
    events = [*board.drain_events(), *advisor.drain_events()]
    details_by_type: dict[str, list[dict[str, object]]] = {}
    for event in events:
        details_by_type.setdefault(event.event_type, []).append(event.details)
        assert all(
            isinstance(value, str | int | float | bool) or value is None
            for value in event.details.values()
        )

    assert set(details_by_type) >= {
        "strategy_phase_changed",
        "combat_mode_changed",
        "command_proposed",
        "command_scheduled",
        "command_suppressed",
        "task_state_changed",
        "strategy_replanned",
    }
    assert set(details_by_type["strategy_phase_changed"][0]) == {"phase"}
    assert set(details_by_type["combat_mode_changed"][0]) == {"mode", "reason"}
    assert set(details_by_type["command_proposed"][0]) == {
        "task_key",
        "source_manager",
        "intent_type",
        "priority",
        "mineral_cost",
        "vespene_cost",
        "supply_cost",
        "uses_build_worker",
        "producer",
        "emergency",
        "attempts",
    }
    assert set(details_by_type["command_scheduled"][0]) == {
        "task_key",
        "intent_type",
        "priority",
        "mineral_cost",
        "vespene_cost",
        "supply_cost",
        "available_minerals",
        "available_vespene",
        "available_supply",
        "remaining_minerals",
        "remaining_vespene",
        "remaining_supply",
        "attempts",
    }
    assert set(details_by_type["command_suppressed"][0]) == {
        "task_key",
        "intent_type",
        "priority",
        "mineral_cost",
        "vespene_cost",
        "supply_cost",
        "available_minerals",
        "available_vespene",
        "available_supply",
        "reason",
        "attempts",
    }
    assert set(details_by_type["task_state_changed"][0]) == {
        "task_key",
        "previous_state",
        "state",
        "reason",
        "attempts",
    }
    assert set(details_by_type["strategy_replanned"][0]) == {
        "task_key",
        "reason",
        "attempts",
    }
