from sc2_ontology_agent.domain.intent import IntentType
from sc2_ontology_agent.policy.hierarchical.blackboard import StrategicBlackboard
from sc2_ontology_agent.policy.hierarchical.commands import (
    ProductionGoal,
    ProductionPhase,
    ResourcePriority,
)

BUILD_ORDER: tuple[ProductionGoal, ...] = (
    ProductionGoal("build:first_depot", IntentType.BUILD_SUPPLY, "supply_depot_count", 1),
    ProductionGoal("build:first_barracks", IntentType.BUILD_BARRACKS, "barracks_count", 1),
    ProductionGoal("build:first_refinery", IntentType.BUILD_REFINERY, "refinery_count", 1),
    ProductionGoal("upgrade:first_orbital", IntentType.UPGRADE_ORBITAL, "orbital_count", 1),
    ProductionGoal("build:expansion", IntentType.EXPAND_COMMAND_CENTER, "townhall_count", 2),
    ProductionGoal("build:second_barracks", IntentType.BUILD_BARRACKS, "barracks_count", 2),
    ProductionGoal(
        "build:first_techlab",
        IntentType.BUILD_TECHLAB,
        "barracks_techlab_count",
        1,
    ),
    ProductionGoal(
        "build:first_reactor",
        IntentType.BUILD_REACTOR,
        "barracks_reactor_count",
        1,
    ),
    ProductionGoal("research:stim", IntentType.RESEARCH_STIM, "stim_researched", True),
)


class ProductionStrategy:
    """Maintain the ordered Terran bio strategy on the domain blackboard."""

    def update(self, board: StrategicBlackboard) -> None:
        for goal in BUILD_ORDER:
            board.ensure_task(goal)

        desired_phase = self._derive_phase(board)
        if desired_phase is not board.production_phase:
            board.production_phase = desired_phase
            board.emit("strategy_phase_changed", phase=desired_phase.value)

        snapshot = board.snapshot
        board.resource_priority = (
            ResourcePriority.GAS
            if snapshot.ready_refinery_count > 0 and snapshot.vespene < 100
            else ResourcePriority.MINERALS
        )

    def _derive_phase(self, board: StrategicBlackboard) -> ProductionPhase:
        snapshot = board.snapshot
        phase = board.production_phase

        if (
            phase is ProductionPhase.OPENING
            and snapshot.ready_barracks_count >= 1
            and snapshot.ready_refinery_count >= 1
            and snapshot.orbital_count >= 1
        ):
            phase = ProductionPhase.EXPANSION
        if (
            phase is ProductionPhase.EXPANSION
            and snapshot.ready_townhall_count >= 2
            and snapshot.ready_barracks_count >= 2
        ):
            phase = ProductionPhase.TECH_UP
        if (
            phase is ProductionPhase.TECH_UP
            and snapshot.barracks_techlab_count >= 1
            and snapshot.barracks_reactor_count >= 1
            and snapshot.stim_researched
        ):
            phase = ProductionPhase.MUSTER
        if (
            phase is ProductionPhase.MUSTER
            and snapshot.army_supply >= board.config.attack_army_supply
        ):
            phase = ProductionPhase.ATTACK
        return phase
