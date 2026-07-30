"""Economy proposals based on the shared strategic snapshot."""

from sc2_ontology_agent.domain.intent import IntentType
from sc2_ontology_agent.domain.tech_tree import STIM_VESPENE_COST
from sc2_ontology_agent.policy.hierarchical.blackboard import StrategicBlackboard
from sc2_ontology_agent.policy.hierarchical.commands import CandidateIntent, ProducerKind
from sc2_ontology_agent.policy.hierarchical.managers import _candidate


class EconomyManager:
    """Maintain worker allocation and SCV production."""

    def propose(self, board: StrategicBlackboard) -> list[CandidateIntent]:
        snapshot = board.snapshot
        candidates: list[CandidateIntent] = []
        if (
            snapshot.idle_worker_count > 0
            or snapshot.mineral_saturation_deficit != 0
            or snapshot.gas_saturation_deficit != 0
        ):
            intent_type = IntentType.DISTRIBUTE_WORKERS
            resource_priority = (
                "gas"
                if snapshot.ready_refinery_count > 0 and snapshot.vespene < STIM_VESPENE_COST
                else "minerals"
            )
            candidates.append(
                _candidate(
                    board,
                    intent_type,
                    80,
                    "worker_distribution_needed",
                    f"{intent_type.value.lower()}:{snapshot.game_loop}",
                    "economy",
                    parameters={"resource_priority": resource_priority},
                )
            )
        if snapshot.worker_count < board.config.worker_limit and snapshot.idle_townhall_count > 0:
            intent_type = IntentType.TRAIN_WORKER
            candidates.append(
                _candidate(
                    board,
                    intent_type,
                    70,
                    "worker_limit_not_reached",
                    f"{intent_type.value.lower()}:{snapshot.game_loop}",
                    "economy",
                    mineral_cost=50,
                    supply_cost=1,
                    producer=ProducerKind.TOWNHALL,
                )
            )
        return candidates
