from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.policy.hierarchical.commands import (
    CandidateIntent,
    ProducerKind,
    ProductionGoal,
    TaskState,
)
from sc2_ontology_agent.policy.hierarchical.scheduler import CommandScheduler

from .conftest import make_snapshot


def make_candidate(
    intent_type: IntentType,
    priority: int,
    task_key: str,
    *,
    minerals: int = 0,
    vespene: int = 0,
    supply: float = 0,
    worker: bool = False,
    uses_worker: bool = False,
    producer: ProducerKind | None = None,
    emergency: bool = False,
) -> CandidateIntent:
    return CandidateIntent(
        intent=MacroIntent(
            intent_type,
            priority,
            task_key,
            100,
            {"task_key": task_key, "source_manager": "test"},
        ),
        task_key=task_key,
        mineral_cost=minerals,
        vespene_cost=vespene,
        supply_cost=supply,
        uses_build_worker=worker,
        uses_worker=uses_worker,
        producer=producer,
        emergency=emergency,
    )


def test_scheduler_reserves_minerals_gas_supply_and_one_worker(blackboard) -> None:
    state = make_snapshot(
        minerals=150,
        vespene=25,
        supply_used=22,
        supply_cap=23,
        idle_barracks_count=1,
        idle_barracks_techlab_count=1,
    )
    candidates = [
        make_candidate(IntentType.BUILD_SUPPLY, 90, "depot", minerals=100, worker=True),
        make_candidate(
            IntentType.BUILD_REFINERY,
            80,
            "refinery",
            minerals=75,
            worker=True,
        ),
        make_candidate(
            IntentType.TRAIN_MARAUDER,
            70,
            "marauder",
            minerals=100,
            vespene=25,
            supply=2,
            producer=ProducerKind.TECHLAB_BARRACKS,
        ),
        make_candidate(
            IntentType.TRAIN_MARINE,
            60,
            "marine",
            minerals=50,
            supply=1,
            producer=ProducerKind.BARRACKS,
        ),
    ]

    selected = CommandScheduler().select(state, candidates, blackboard)

    assert [intent.intent_type for intent in selected] == [
        IntentType.BUILD_SUPPLY,
        IntentType.TRAIN_MARINE,
    ]


def test_emergency_defense_preempts_expansion(blackboard) -> None:
    state = make_snapshot(minerals=400, enemy_units_near_base=3)
    candidates = [
        make_candidate(
            IntentType.EXPAND_COMMAND_CENTER,
            40,
            "expand",
            minerals=400,
            worker=True,
        ),
        make_candidate(
            IntentType.DEFEND_BASE,
            100,
            "defend",
            emergency=True,
        ),
    ]

    selected = CommandScheduler().select(state, candidates, blackboard)

    assert [intent.intent_type for intent in selected] == [IntentType.DEFEND_BASE]
    suppressed = [
        event for event in blackboard.drain_events() if event.event_type == "command_suppressed"
    ]
    assert suppressed[-1].details["reason"] == "emergency_preempts_expansion_or_tech"


def test_scheduler_limits_shared_producer_capacity(blackboard) -> None:
    state = make_snapshot(
        minerals=200,
        supply_cap=50,
        idle_barracks_count=1,
        idle_barracks_techlab_count=1,
    )
    candidates = [
        make_candidate(
            IntentType.TRAIN_MARAUDER,
            70,
            "marauder",
            producer=ProducerKind.TECHLAB_BARRACKS,
        ),
        make_candidate(
            IntentType.TRAIN_MARINE,
            60,
            "marine",
            producer=ProducerKind.BARRACKS,
        ),
    ]

    assert len(CommandScheduler().select(state, candidates, blackboard)) == 1


def test_scheduler_marks_existing_task_scheduled_and_skips_pending_action(blackboard) -> None:
    goal = ProductionGoal(
        "build:first_depot",
        IntentType.BUILD_SUPPLY,
        "supply_depot_count",
        1,
    )
    blackboard.ensure_task(goal)
    state = make_snapshot(pending_actions=(IntentType.TRAIN_MARINE.value,))
    candidates = [
        make_candidate(IntentType.BUILD_SUPPLY, 80, goal.key),
        make_candidate(IntentType.TRAIN_MARINE, 70, "marine"),
    ]

    selected = CommandScheduler().select(state, candidates, blackboard)

    assert [intent.intent_type for intent in selected] == [IntentType.BUILD_SUPPLY]
    assert blackboard.tasks[goal.key].state is TaskState.SCHEDULED
    events = blackboard.drain_events()
    assert any(event.event_type == "command_scheduled" for event in events)
    assert any(
        event.event_type == "command_suppressed" and event.details["reason"] == "pending_action"
        for event in events
    )


def test_scheduler_uses_input_order_to_break_equal_priority_ties(blackboard) -> None:
    state = make_snapshot(minerals=100)
    candidates = [
        make_candidate(IntentType.TRAIN_MARINE, 60, "first", minerals=100),
        make_candidate(IntentType.TRAIN_WORKER, 60, "second", minerals=100),
    ]

    selected = CommandScheduler().select(state, candidates, blackboard)

    assert [intent.reason for intent in selected] == ["first"]


def test_scheduler_returns_idle_when_every_candidate_is_unschedulable(blackboard) -> None:
    state = make_snapshot(minerals=0)

    selected = CommandScheduler().select(
        state,
        [make_candidate(IntentType.TRAIN_MARINE, 60, "marine", minerals=50)],
        blackboard,
    )

    assert [intent.intent_type for intent in selected] == [IntentType.IDLE]


def test_scheduler_reserves_worker_for_higher_priority_construction(blackboard) -> None:
    state = make_snapshot(minerals=500, worker_count=12)
    candidates = [
        make_candidate(
            IntentType.BUILD_BARRACKS,
            85,
            "build:first_barracks",
            minerals=150,
            worker=True,
        ),
        make_candidate(
            IntentType.DISTRIBUTE_WORKERS,
            80,
            "distribute",
            uses_worker=True,
        ),
        make_candidate(
            IntentType.SCOUT_ENEMY_START,
            50,
            "scout",
            uses_worker=True,
        ),
    ]

    selected = CommandScheduler().select(state, candidates, blackboard)

    assert [intent.intent_type for intent in selected] == [IntentType.BUILD_BARRACKS]
