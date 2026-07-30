from sc2_ontology_agent.config import BotConfig
from sc2_ontology_agent.domain.intent import IntentType
from sc2_ontology_agent.domain.records import ExecutionResult, ExecutionStatus
from sc2_ontology_agent.policy.hierarchical.advisor import HierarchicalRulePolicy

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
