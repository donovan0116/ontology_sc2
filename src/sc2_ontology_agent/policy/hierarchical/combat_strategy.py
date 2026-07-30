from sc2_ontology_agent.policy.hierarchical.blackboard import StrategicBlackboard
from sc2_ontology_agent.policy.hierarchical.commands import CombatMode, ProductionPhase


class CombatStrategy:
    """Select the blackboard combat mode from strategic phase and base threats."""

    def update(self, board: StrategicBlackboard) -> None:
        snapshot = board.snapshot
        if snapshot.enemy_units_near_base > 0:
            if board.combat_mode is not CombatMode.DEFEND:
                board.mode_before_defense = board.combat_mode
                board.combat_mode = CombatMode.DEFEND
                board.emit("combat_mode_changed", mode="defend", reason="base_threat")
            return

        if board.combat_mode is CombatMode.DEFEND:
            restored = board.mode_before_defense
            board.combat_mode = restored
            board.emit("combat_mode_changed", mode=restored.value, reason="threat_cleared")
            return

        desired = {
            ProductionPhase.OPENING: CombatMode.DEVELOP,
            ProductionPhase.EXPANSION: CombatMode.DEVELOP,
            ProductionPhase.TECH_UP: CombatMode.DEVELOP,
            ProductionPhase.MUSTER: CombatMode.RALLY,
            ProductionPhase.ATTACK: CombatMode.ATTACK,
        }[board.production_phase]
        if desired is not board.combat_mode:
            board.combat_mode = desired
            board.emit("combat_mode_changed", mode=desired.value, reason="production_phase")
