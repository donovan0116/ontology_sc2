import pytest

from sc2_ontology_agent.domain.intent import IntentType
from sc2_ontology_agent.policy.hierarchical.combat_strategy import CombatStrategy
from sc2_ontology_agent.policy.hierarchical.commands import (
    CandidateIntent,
    CombatMode,
    ProducerKind,
    ProductionPhase,
    TaskState,
)
from sc2_ontology_agent.policy.hierarchical.managers.combat import CombatManager
from sc2_ontology_agent.policy.hierarchical.managers.construction import ConstructionManager
from sc2_ontology_agent.policy.hierarchical.managers.economy import EconomyManager
from sc2_ontology_agent.policy.hierarchical.managers.production import ProductionManager
from sc2_ontology_agent.policy.hierarchical.managers.scout import ScoutManager
from sc2_ontology_agent.policy.hierarchical.managers.technology import TechnologyManager
from sc2_ontology_agent.policy.hierarchical.production_strategy import ProductionStrategy

from .conftest import make_snapshot


def types(candidates: list[CandidateIntent]) -> list[IntentType]:
    return [candidate.intent.intent_type for candidate in candidates]


def test_economy_proposes_worker_and_gas_biased_distribution(blackboard) -> None:
    blackboard.update(
        make_snapshot(
            worker_count=20,
            idle_worker_count=1,
            idle_townhall_count=1,
            ready_refinery_count=1,
            gas_saturation_deficit=3,
            vespene=0,
        )
    )

    candidates = EconomyManager().propose(blackboard)

    assert types(candidates) == [
        IntentType.DISTRIBUTE_WORKERS,
        IntentType.TRAIN_WORKER,
    ]
    assert candidates[0].intent.parameters["resource_priority"] == "gas"
    assert candidates[1].mineral_cost == 50
    assert candidates[1].supply_cost == 1
    assert candidates[1].producer is ProducerKind.TOWNHALL


def test_construction_proposes_only_first_incomplete_build_goal(blackboard) -> None:
    ProductionStrategy().update(blackboard)
    blackboard.update(make_snapshot(supply_depot_count=1))

    candidates = ConstructionManager().propose(blackboard)

    assert types(candidates) == [IntentType.BUILD_BARRACKS]
    assert candidates[0].task_key == "build:first_barracks"
    assert candidates[0].mineral_cost == 150
    assert candidates[0].uses_build_worker is True


def test_construction_uses_an_addonless_barracks_without_reserving_a_worker(
    blackboard,
) -> None:
    ProductionStrategy().update(blackboard)
    blackboard.update(
        make_snapshot(
            supply_depot_count=1,
            barracks_count=2,
            refinery_count=1,
            orbital_count=1,
            townhall_count=2,
        )
    )

    candidate = ConstructionManager().propose(blackboard)[0]

    assert candidate.intent.intent_type is IntentType.BUILD_TECHLAB
    assert candidate.mineral_cost == 50
    assert candidate.vespene_cost == 25
    assert candidate.producer is ProducerKind.ADDONLESS_BARRACKS
    assert candidate.uses_build_worker is False


def test_construction_prioritizes_the_first_depot_when_supply_is_low(blackboard) -> None:
    ProductionStrategy().update(blackboard)
    blackboard.update(make_snapshot(supply_used=18, supply_cap=23))

    candidate = ConstructionManager().propose(blackboard)[0]

    assert candidate.intent.intent_type is IntentType.BUILD_SUPPLY
    assert candidate.intent.priority == 90


def test_construction_waits_for_worker_threshold_before_expansion(blackboard) -> None:
    ProductionStrategy().update(blackboard)
    before_threshold = make_snapshot(
        supply_depot_count=1,
        barracks_count=1,
        refinery_count=1,
        orbital_count=1,
        townhall_count=1,
        worker_count=blackboard.config.expansion_worker_threshold - 1,
    )
    blackboard.update(before_threshold)

    assert ConstructionManager().propose(blackboard) == []
    assert blackboard.tasks["build:expansion"].state is TaskState.PLANNED
    assert blackboard.tasks["build:second_barracks"].state is TaskState.PLANNED

    blackboard.update(
        make_snapshot(
            supply_depot_count=1,
            barracks_count=1,
            refinery_count=1,
            orbital_count=1,
            townhall_count=1,
            worker_count=blackboard.config.expansion_worker_threshold,
        )
    )

    candidates = ConstructionManager().propose(blackboard)

    assert types(candidates) == [IntentType.EXPAND_COMMAND_CENTER]
    assert candidates[0].task_key == "build:expansion"


@pytest.mark.parametrize(
    "marine_count,marauder_count,expected",
    [
        (2, 1, IntentType.TRAIN_MARINE),
        (4, 1, IntentType.TRAIN_MARAUDER),
    ],
)
def test_production_maintains_two_to_one_ratio(
    blackboard,
    marine_count: int,
    marauder_count: int,
    expected: IntentType,
) -> None:
    blackboard.update(
        make_snapshot(
            ready_barracks_count=2,
            idle_barracks_count=2,
            idle_barracks_techlab_count=1,
            marine_count=marine_count,
            marauder_count=marauder_count,
            supply_cap=100,
        )
    )

    candidate = ProductionManager().propose(blackboard)[0]

    assert candidate.intent.intent_type is expected
    assert candidate.mineral_cost == (100 if expected is IntentType.TRAIN_MARAUDER else 50)
    assert candidate.producer is (
        ProducerKind.TECHLAB_BARRACKS
        if expected is IntentType.TRAIN_MARAUDER
        else ProducerKind.BARRACKS
    )


def test_technology_proposes_stim_when_techlab_is_ready(blackboard) -> None:
    ProductionStrategy().update(blackboard)
    blackboard.update(
        make_snapshot(
            supply_depot_count=1,
            barracks_count=2,
            refinery_count=1,
            orbital_count=1,
            townhall_count=2,
            barracks_techlab_count=1,
            barracks_reactor_count=1,
            idle_barracks_techlab_count=1,
            stim_researched=False,
            stim_pending=False,
        )
    )

    candidate = TechnologyManager().propose(blackboard)[0]

    assert candidate.intent.intent_type is IntentType.RESEARCH_STIM
    assert candidate.vespene_cost == 100
    assert candidate.producer is ProducerKind.TECHLAB


def test_scout_is_one_shot_after_time_window(blackboard) -> None:
    blackboard.update(make_snapshot(game_time_seconds=90.0))

    candidates = ScoutManager().propose(blackboard)
    blackboard.scout_accepted = True

    assert types(candidates) == [IntentType.SCOUT_ENEMY_START]
    assert candidates[0].task_key == "scout:enemy_start"
    assert ScoutManager().propose(blackboard) == []


def test_combat_defense_has_emergency_candidate(blackboard) -> None:
    blackboard.update(make_snapshot(enemy_units_near_base=2, marine_count=4))
    CombatStrategy().update(blackboard)

    candidate = CombatManager().propose(blackboard)[0]

    assert candidate.intent.intent_type is IntentType.DEFEND_BASE
    assert candidate.emergency is True


def test_combat_waits_for_reinforcement_supply_after_first_attack(blackboard) -> None:
    blackboard.combat_mode = CombatMode.ATTACK
    blackboard.attack_started = True
    blackboard.update(make_snapshot(army_supply=blackboard.config.reinforcement_army_supply - 1))

    assert CombatManager().propose(blackboard) == []

    blackboard.update(make_snapshot(army_supply=blackboard.config.reinforcement_army_supply))
    candidate = CombatManager().propose(blackboard)[0]

    assert candidate.intent.intent_type is IntentType.ATTACK_ENEMY
    assert candidate.intent.parameters["reinforcement"] is True


def test_combat_first_attack_remains_governed_by_attack_phase_threshold(blackboard) -> None:
    strategy = CombatStrategy()
    production_strategy = ProductionStrategy()
    blackboard.production_phase = ProductionPhase.MUSTER
    blackboard.update(make_snapshot(army_supply=blackboard.config.attack_army_supply - 1))
    production_strategy.update(blackboard)
    strategy.update(blackboard)

    assert blackboard.combat_mode is CombatMode.RALLY

    blackboard.update(make_snapshot(army_supply=blackboard.config.attack_army_supply))
    production_strategy.update(blackboard)
    strategy.update(blackboard)
    candidate = CombatManager().propose(blackboard)[0]

    assert blackboard.combat_mode is CombatMode.ATTACK
    assert candidate.intent.intent_type is IntentType.ATTACK_ENEMY
    assert candidate.intent.parameters["reinforcement"] is False


def test_all_manager_candidates_include_scalar_task_metadata(blackboard) -> None:
    blackboard.update(
        make_snapshot(
            idle_worker_count=1,
            idle_townhall_count=1,
            ready_barracks_count=1,
            idle_barracks_count=1,
            game_time_seconds=90.0,
        )
    )

    candidates = [
        *EconomyManager().propose(blackboard),
        *ProductionManager().propose(blackboard),
        *ScoutManager().propose(blackboard),
        *CombatManager().propose(blackboard),
    ]

    for candidate in candidates:
        parameters = candidate.intent.parameters
        assert parameters["task_key"] == candidate.task_key
        assert isinstance(parameters["task_key"], str)
        assert isinstance(parameters["source_manager"], str)
