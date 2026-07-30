from sc2_ontology_agent.policy.hierarchical.blackboard import StrategicBlackboard
from sc2_ontology_agent.policy.hierarchical.combat_strategy import CombatStrategy
from sc2_ontology_agent.policy.hierarchical.commands import CombatMode, ProductionPhase
from sc2_ontology_agent.policy.hierarchical.production_strategy import ProductionStrategy

from .conftest import make_snapshot


def test_production_strategy_populates_approved_build_order(
    blackboard: StrategicBlackboard,
) -> None:
    ProductionStrategy().update(blackboard)

    assert [goal.key for goal in blackboard.production_goals] == [
        "build:first_depot",
        "build:first_barracks",
        "build:first_refinery",
        "upgrade:first_orbital",
        "build:expansion",
        "build:second_barracks",
        "build:first_techlab",
        "build:first_reactor",
        "research:stim",
    ]


def test_production_strategy_advances_all_phases(
    blackboard: StrategicBlackboard,
) -> None:
    strategy = ProductionStrategy()
    observations = [
        (
            make_snapshot(
                barracks_count=1,
                ready_barracks_count=1,
                refinery_count=1,
                ready_refinery_count=1,
                orbital_count=1,
            ),
            ProductionPhase.EXPANSION,
        ),
        (
            make_snapshot(
                barracks_count=2,
                ready_barracks_count=2,
                refinery_count=1,
                orbital_count=1,
                townhall_count=2,
                ready_townhall_count=2,
            ),
            ProductionPhase.TECH_UP,
        ),
        (
            make_snapshot(
                barracks_count=2,
                townhall_count=2,
                barracks_techlab_count=1,
                barracks_reactor_count=1,
                stim_researched=True,
            ),
            ProductionPhase.MUSTER,
        ),
        (
            make_snapshot(
                barracks_techlab_count=1,
                barracks_reactor_count=1,
                stim_researched=True,
                army_supply=24,
            ),
            ProductionPhase.ATTACK,
        ),
    ]
    for snapshot, expected in observations:
        blackboard.update(snapshot)
        strategy.update(blackboard)
        assert blackboard.production_phase is expected


def test_combat_strategy_defense_preempts_and_then_restores_rally(
    blackboard: StrategicBlackboard,
) -> None:
    strategy = CombatStrategy()
    blackboard.production_phase = ProductionPhase.MUSTER
    strategy.update(blackboard)
    assert blackboard.combat_mode is CombatMode.RALLY

    blackboard.update(make_snapshot(enemy_units_near_base=3))
    strategy.update(blackboard)
    assert blackboard.combat_mode is CombatMode.DEFEND

    blackboard.update(make_snapshot(game_loop=120, enemy_units_near_base=0))
    strategy.update(blackboard)
    assert blackboard.combat_mode is CombatMode.RALLY
