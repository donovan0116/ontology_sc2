from sc2_ontology_agent.config import BotConfig
from sc2_ontology_agent.domain.intent import IntentType
from sc2_ontology_agent.domain.records import ExecutionResult, ExecutionStatus
from sc2_ontology_agent.policy.hierarchical.advisor import HierarchicalRulePolicy
from sc2_ontology_agent.policy.hierarchical.commands import TaskState

from .conftest import make_snapshot


def test_advisor_progresses_from_opening_to_stim_timing_attack() -> None:
    advisor = HierarchicalRulePolicy(BotConfig())
    opening = advisor.recommend(
        make_snapshot(
            minerals=500,
            supply_used=14,
            supply_cap=15,
        )
    )
    assert IntentType.BUILD_SUPPLY in {intent.intent_type for intent in opening}

    tech = advisor.recommend(
        make_snapshot(
            game_loop=500,
            game_time_seconds=180,
            minerals=500,
            vespene=200,
            supply_cap=60,
            worker_count=30,
            townhall_count=2,
            ready_townhall_count=2,
            orbital_count=1,
            refinery_count=1,
            ready_refinery_count=1,
            supply_depot_count=3,
            ready_supply_depot_count=3,
            barracks_count=2,
            ready_barracks_count=2,
            barracks_techlab_count=1,
            barracks_reactor_count=1,
            idle_barracks_techlab_count=1,
        )
    )
    assert IntentType.RESEARCH_STIM in {intent.intent_type for intent in tech}

    attack = advisor.recommend(
        make_snapshot(
            game_loop=1000,
            game_time_seconds=300,
            minerals=500,
            vespene=200,
            supply_cap=100,
            worker_count=44,
            townhall_count=2,
            barracks_count=2,
            barracks_techlab_count=1,
            barracks_reactor_count=1,
            stim_researched=True,
            army_supply=24,
            marine_count=16,
            marauder_count=4,
        )
    )
    assert IntentType.ATTACK_ENEMY in {intent.intent_type for intent in attack}


def test_execution_feedback_updates_task_and_events() -> None:
    advisor = HierarchicalRulePolicy(BotConfig())
    intents = advisor.recommend(make_snapshot(minerals=500))
    depot = next(intent for intent in intents if intent.intent_type is IntentType.BUILD_SUPPLY)

    advisor.observe_execution(
        depot,
        ExecutionResult(ExecutionStatus.ACCEPTED),
    )

    assert advisor.blackboard.tasks["build:first_depot"].state.value == "accepted"
    assert "task_state_changed" in {event.event_type for event in advisor.drain_events()}


def test_opening_waits_for_ready_depot_before_scheduling_barracks() -> None:
    advisor = HierarchicalRulePolicy(BotConfig())
    opening = advisor.recommend(
        make_snapshot(
            minerals=500,
            supply_used=14,
            supply_cap=15,
        )
    )
    depot = next(intent for intent in opening if intent.intent_type is IntentType.BUILD_SUPPLY)
    advisor.observe_execution(depot, ExecutionResult(ExecutionStatus.ACCEPTED))

    while_building = advisor.recommend(
        make_snapshot(
            game_loop=104,
            minerals=400,
            supply_used=14,
            supply_cap=15,
            supply_depot_count=1,
            ready_supply_depot_count=0,
            pending_actions=(IntentType.BUILD_SUPPLY.value,),
        )
    )

    assert advisor.blackboard.tasks["build:first_depot"].state is TaskState.ACCEPTED
    assert IntentType.BUILD_BARRACKS not in {intent.intent_type for intent in while_building}

    after_completion = advisor.recommend(
        make_snapshot(
            game_loop=108,
            minerals=400,
            supply_used=14,
            supply_cap=23,
            supply_depot_count=1,
            ready_supply_depot_count=1,
        )
    )

    assert advisor.blackboard.tasks["build:first_depot"].state is TaskState.COMPLETED
    assert IntentType.BUILD_BARRACKS in {intent.intent_type for intent in after_completion}
    queue_head = next(
        goal
        for goal in advisor.blackboard.production_goals
        if advisor.blackboard.tasks[goal.key].state is not TaskState.COMPLETED
    )
    assert advisor.blackboard.tasks[queue_head.key].state is not TaskState.FAILED


def test_affordable_orbital_precedes_worker_then_worker_resumes() -> None:
    advisor = HierarchicalRulePolicy(BotConfig())
    orbital_snapshot = make_snapshot(
        game_loop=104,
        minerals=200,
        supply_cap=30,
        worker_count=12,
        idle_townhall_count=1,
        supply_depot_count=1,
        ready_supply_depot_count=1,
        barracks_count=1,
        ready_barracks_count=1,
        refinery_count=1,
        ready_refinery_count=1,
    )
    advisor.recommend(
        make_snapshot(
            game_loop=100,
            minerals=200,
            supply_cap=30,
            worker_count=12,
            idle_townhall_count=1,
            supply_depot_count=1,
            ready_supply_depot_count=1,
            barracks_count=1,
            ready_barracks_count=1,
            refinery_count=1,
            ready_refinery_count=1,
        )
    )

    before_upgrade = advisor.recommend(orbital_snapshot)

    assert [intent.intent_type for intent in before_upgrade] == [IntentType.UPGRADE_ORBITAL]
    advisor.observe_execution(
        before_upgrade[0],
        ExecutionResult(ExecutionStatus.ACCEPTED),
    )

    after_upgrade = advisor.recommend(
        make_snapshot(
            game_loop=108,
            minerals=50,
            supply_cap=30,
            worker_count=12,
            idle_townhall_count=1,
            supply_depot_count=1,
            ready_supply_depot_count=1,
            barracks_count=1,
            ready_barracks_count=1,
            refinery_count=1,
            ready_refinery_count=1,
            orbital_count=1,
        )
    )

    assert IntentType.TRAIN_WORKER in {intent.intent_type for intent in after_upgrade}


def test_scout_failure_honors_cooldown_then_exhausts() -> None:
    advisor = HierarchicalRulePolicy(
        BotConfig(
            scout_start_time_seconds=1,
            task_retry_limit=1,
            task_retry_cooldown_steps=2,
        )
    )
    first = next(
        intent
        for intent in advisor.recommend(make_snapshot(minerals=0))
        if intent.intent_type is IntentType.SCOUT_ENEMY_START
    )
    advisor.observe_execution(
        first,
        ExecutionResult(ExecutionStatus.FAILED, "scout_command_rejected"),
    )

    during_cooldown = advisor.recommend(make_snapshot(game_loop=104, minerals=0))
    assert IntentType.SCOUT_ENEMY_START not in {intent.intent_type for intent in during_cooldown}

    retry = next(
        intent
        for intent in advisor.recommend(make_snapshot(game_loop=108, minerals=0))
        if intent.intent_type is IntentType.SCOUT_ENEMY_START
    )
    advisor.observe_execution(
        retry,
        ExecutionResult(ExecutionStatus.FAILED, "scout_command_rejected"),
    )

    after_exhaustion = advisor.recommend(make_snapshot(game_loop=116, minerals=0))
    assert IntentType.SCOUT_ENEMY_START not in {intent.intent_type for intent in after_exhaustion}
    scout = advisor.blackboard.tasks["scout:enemy_start"]
    assert scout.state is TaskState.FAILED
    assert scout.attempts == 2


def test_accepted_scout_task_completes_and_is_not_repeated() -> None:
    advisor = HierarchicalRulePolicy(BotConfig(scout_start_time_seconds=1))
    scout = next(
        intent
        for intent in advisor.recommend(make_snapshot(minerals=0))
        if intent.intent_type is IntentType.SCOUT_ENEMY_START
    )

    advisor.observe_execution(
        scout,
        ExecutionResult(ExecutionStatus.ACCEPTED),
    )

    assert advisor.blackboard.tasks["scout:enemy_start"].state is TaskState.COMPLETED
    events = [
        event
        for event in advisor.drain_events()
        if event.event_type == "task_state_changed"
        and event.details["task_key"] == "scout:enemy_start"
    ]
    assert [event.details["state"] for event in events][-2:] == [
        TaskState.ACCEPTED.value,
        TaskState.COMPLETED.value,
    ]
    later = advisor.recommend(make_snapshot(game_loop=104, minerals=0))
    assert IntentType.SCOUT_ENEMY_START not in {intent.intent_type for intent in later}


def test_worker_fairness_orders_construction_then_scout_then_distribution() -> None:
    advisor = HierarchicalRulePolicy(BotConfig(scout_start_time_seconds=11))

    construction = advisor.recommend(
        make_snapshot(
            game_loop=100,
            game_time_seconds=10.0,
            minerals=500,
            mineral_saturation_deficit=2,
            gas_saturation_deficit=3,
        )
    )

    assert construction[0].intent_type is IntentType.BUILD_SUPPLY
    assert IntentType.DISTRIBUTE_WORKERS not in {intent.intent_type for intent in construction}
    depot = next(intent for intent in construction if intent.intent_type is IntentType.BUILD_SUPPLY)
    advisor.observe_execution(
        depot,
        ExecutionResult(ExecutionStatus.ACCEPTED),
    )

    scouting = advisor.recommend(
        make_snapshot(
            game_loop=132,
            game_time_seconds=11.0,
            minerals=400,
            mineral_saturation_deficit=2,
            gas_saturation_deficit=3,
            supply_depot_count=1,
            ready_supply_depot_count=0,
            pending_actions=(IntentType.BUILD_SUPPLY.value,),
        )
    )

    assert IntentType.SCOUT_ENEMY_START in {intent.intent_type for intent in scouting}
    assert IntentType.DISTRIBUTE_WORKERS not in {intent.intent_type for intent in scouting}
    scout_proposal = next(
        event
        for event in advisor.drain_events()
        if event.event_type == "command_proposed"
        and event.details["intent_type"] == IntentType.SCOUT_ENEMY_START.value
    )
    assert scout_proposal.details["uses_worker"] is True
    assert scout_proposal.details["uses_build_worker"] is False
    scout = next(
        intent for intent in scouting if intent.intent_type is IntentType.SCOUT_ENEMY_START
    )
    advisor.observe_execution(
        scout,
        ExecutionResult(ExecutionStatus.ACCEPTED),
    )
    assert advisor.blackboard.tasks["scout:enemy_start"].state is TaskState.COMPLETED

    distribution = advisor.recommend(
        make_snapshot(
            game_loop=164,
            game_time_seconds=12.0,
            minerals=400,
            mineral_saturation_deficit=2,
            gas_saturation_deficit=3,
            supply_depot_count=1,
            ready_supply_depot_count=0,
            pending_actions=(IntentType.BUILD_SUPPLY.value,),
        )
    )

    assert IntentType.DISTRIBUTE_WORKERS in {intent.intent_type for intent in distribution}
    assert IntentType.SCOUT_ENEMY_START not in {intent.intent_type for intent in distribution}
