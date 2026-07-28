from dataclasses import replace

from sc2_ontology_agent.config import BotConfig
from sc2_ontology_agent.domain.intent import IntentType
from sc2_ontology_agent.domain.state import GameSnapshot
from sc2_ontology_agent.policy.simple_rule_policy import SimpleRulePolicy


def snapshot(**changes: object) -> GameSnapshot:
    base = GameSnapshot(
        game_loop=100,
        game_time_seconds=4.5,
        minerals=500,
        vespene=0,
        supply_used=12,
        supply_cap=15,
        worker_count=12,
        marine_count=0,
        barracks_count=0,
        supply_depot_count=0,
        enemy_units_visible=0,
        enemy_structures_visible=0,
        pending_actions=(),
        idle_worker_count=0,
        pending_worker_count=0,
        pending_marine_count=0,
        ready_supply_depot_count=0,
        ready_barracks_count=0,
        idle_townhall_count=1,
        idle_barracks_count=0,
        attack_started=False,
    )
    return replace(base, **changes)


def intent_types(state: GameSnapshot, config: BotConfig | None = None) -> list[IntentType]:
    intents = SimpleRulePolicy(config or BotConfig()).recommend(state)
    return [intent.intent_type for intent in intents]


def test_low_supply_triggers_build_supply() -> None:
    assert IntentType.BUILD_SUPPLY in intent_types(snapshot(supply_used=13, supply_cap=15))


def test_worker_below_limit_triggers_train_worker() -> None:
    state = snapshot(supply_used=5, supply_cap=15, worker_count=10)
    assert IntentType.TRAIN_WORKER in intent_types(state)


def test_ready_depot_and_missing_barracks_triggers_build_barracks() -> None:
    state = snapshot(
        supply_used=5,
        supply_cap=23,
        worker_count=22,
        supply_depot_count=1,
        ready_supply_depot_count=1,
    )
    assert IntentType.BUILD_BARRACKS in intent_types(state)


def test_marine_threshold_triggers_attack() -> None:
    state = snapshot(
        supply_used=20,
        supply_cap=31,
        worker_count=22,
        marine_count=10,
        barracks_count=1,
        ready_supply_depot_count=1,
        ready_barracks_count=1,
    )
    assert IntentType.ATTACK_ENEMY_START in intent_types(state)


def test_idle_reinforcement_triggers_attack_after_first_wave() -> None:
    state = snapshot(
        worker_count=22,
        marine_count=10,
        idle_marine_count=1,
        attack_started=True,
    )
    assert IntentType.ATTACK_ENEMY_START in intent_types(state)


def test_pending_build_prevents_duplicate_intent() -> None:
    state = snapshot(
        supply_used=14,
        supply_cap=15,
        pending_actions=(IntentType.BUILD_SUPPLY.value,),
    )
    assert IntentType.BUILD_SUPPLY not in intent_types(state)


def test_intents_are_unique_and_priority_sorted() -> None:
    intents = SimpleRulePolicy(BotConfig()).recommend(
        snapshot(idle_worker_count=1, supply_used=14, supply_cap=15)
    )

    priorities = [intent.priority for intent in intents]
    types = [intent.intent_type for intent in intents]
    assert priorities == sorted(priorities, reverse=True)
    assert len(types) == len(set(types))


def test_budget_prevents_conflicting_mineral_spend() -> None:
    state = snapshot(
        minerals=100,
        supply_used=14,
        supply_cap=15,
        idle_worker_count=0,
    )

    assert intent_types(state) == [IntentType.BUILD_SUPPLY]


def test_only_one_worker_construction_is_scheduled_per_decision() -> None:
    state = snapshot(
        minerals=500,
        supply_used=14,
        supply_cap=15,
        worker_count=22,
        barracks_count=1,
        supply_depot_count=1,
        ready_supply_depot_count=1,
    )
    config = BotConfig(max_barracks=2)

    types = intent_types(state, config)

    assert IntentType.BUILD_SUPPLY in types
    assert IntentType.BUILD_BARRACKS not in types


def test_no_rule_returns_idle() -> None:
    state = snapshot(
        minerals=0,
        supply_used=10,
        supply_cap=20,
        worker_count=22,
        barracks_count=1,
        supply_depot_count=1,
        ready_supply_depot_count=1,
        ready_barracks_count=1,
        idle_townhall_count=0,
        idle_barracks_count=0,
        attack_started=True,
    )
    assert intent_types(state) == [IntentType.IDLE]
