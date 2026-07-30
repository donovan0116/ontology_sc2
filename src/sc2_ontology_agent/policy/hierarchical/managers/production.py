"""Barracks unit-production proposals."""

from sc2_ontology_agent.domain.intent import IntentType
from sc2_ontology_agent.policy.hierarchical.blackboard import StrategicBlackboard
from sc2_ontology_agent.policy.hierarchical.commands import CandidateIntent, ProducerKind
from sc2_ontology_agent.policy.hierarchical.managers import _candidate


class ProductionManager:
    """Maintain the configured Marine-to-Marauder production ratio."""

    def propose(self, board: StrategicBlackboard) -> list[CandidateIntent]:
        snapshot = board.snapshot
        if snapshot.ready_barracks_count == 0:
            return []

        use_marauder = (
            snapshot.marine_count > snapshot.marauder_count * board.config.marine_to_marauder_ratio
        )
        if use_marauder:
            intent_type = IntentType.TRAIN_MARAUDER
            mineral_cost = 100
            vespene_cost = 25
            supply_cost = 2
            producer = ProducerKind.TECHLAB_BARRACKS
        else:
            intent_type = IntentType.TRAIN_MARINE
            mineral_cost = 50
            vespene_cost = 0
            supply_cost = 1
            producer = ProducerKind.BARRACKS
        return [
            _candidate(
                board,
                intent_type,
                60,
                "maintain_bio_unit_ratio",
                f"{intent_type.value.lower()}:{snapshot.game_loop}",
                "production",
                mineral_cost=mineral_cost,
                vespene_cost=vespene_cost,
                supply_cost=supply_cost,
                producer=producer,
            )
        ]
