"""Combat-mode proposals."""

from sc2_ontology_agent.domain.intent import IntentType
from sc2_ontology_agent.policy.hierarchical.blackboard import StrategicBlackboard
from sc2_ontology_agent.policy.hierarchical.commands import CandidateIntent, CombatMode
from sc2_ontology_agent.policy.hierarchical.managers import _candidate

_MODE_INTENT_TYPES: dict[CombatMode, IntentType] = {
    CombatMode.RALLY: IntentType.RALLY_ARMY,
    CombatMode.DEFEND: IntentType.DEFEND_BASE,
    CombatMode.ATTACK: IntentType.ATTACK_ENEMY,
}


class CombatManager:
    """Translate the strategy combat mode into an executable macro intent."""

    def propose(self, board: StrategicBlackboard) -> list[CandidateIntent]:
        intent_type = _MODE_INTENT_TYPES.get(board.combat_mode)
        if intent_type is None:
            return []

        snapshot = board.snapshot
        emergency = board.combat_mode is CombatMode.DEFEND
        if (
            board.combat_mode is CombatMode.ATTACK
            and board.attack_started
            and snapshot.army_supply < board.config.reinforcement_army_supply
        ):
            return []
        parameters = (
            {"reinforcement": board.attack_started}
            if board.combat_mode is CombatMode.ATTACK
            else None
        )
        return [
            _candidate(
                board,
                intent_type,
                100 if emergency else 80 if board.combat_mode is CombatMode.ATTACK else 50,
                f"combat_mode_{board.combat_mode.value}",
                f"{intent_type.value.lower()}:{snapshot.game_loop}",
                "combat",
                parameters=parameters,
                emergency=emergency,
            )
        ]
