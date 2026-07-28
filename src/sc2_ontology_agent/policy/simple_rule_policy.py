from __future__ import annotations

from dataclasses import dataclass

from sc2_ontology_agent.config import BotConfig
from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.domain.state import GameSnapshot


@dataclass(frozen=True, slots=True)
class _Candidate:
    intent_type: IntentType
    priority: int
    reason: str
    mineral_cost: int = 0
    supply_cost: float = 0.0
    uses_build_worker: bool = False


class SimpleRulePolicy:
    """Deterministic V0.1 macro policy with conservative same-step budgeting."""

    def __init__(self, config: BotConfig) -> None:
        self._config = config

    def recommend(self, snapshot: GameSnapshot) -> list[MacroIntent]:
        pending = set(snapshot.pending_actions)
        candidates: list[_Candidate] = []

        if snapshot.idle_worker_count > 0:
            candidates.append(
                _Candidate(IntentType.DISTRIBUTE_WORKERS, 100, "idle_workers_available")
            )

        if (
            snapshot.supply_left <= self._config.supply_buffer
            and IntentType.BUILD_SUPPLY.value not in pending
        ):
            candidates.append(
                _Candidate(
                    IntentType.BUILD_SUPPLY,
                    90,
                    "supply_buffer_reached",
                    mineral_cost=100,
                    uses_build_worker=True,
                )
            )

        projected_workers = snapshot.worker_count + snapshot.pending_worker_count
        if (
            projected_workers < self._config.worker_limit
            and snapshot.idle_townhall_count > 0
            and IntentType.TRAIN_WORKER.value not in pending
        ):
            candidates.append(
                _Candidate(
                    IntentType.TRAIN_WORKER,
                    80,
                    "worker_limit_not_reached",
                    mineral_cost=50,
                    supply_cost=1,
                )
            )

        if (
            snapshot.ready_supply_depot_count > 0
            and snapshot.barracks_count < self._config.max_barracks
            and IntentType.BUILD_BARRACKS.value not in pending
        ):
            candidates.append(
                _Candidate(
                    IntentType.BUILD_BARRACKS,
                    70,
                    "production_capacity_missing",
                    mineral_cost=150,
                    uses_build_worker=True,
                )
            )

        if (
            snapshot.ready_barracks_count > 0
            and snapshot.idle_barracks_count > 0
            and IntentType.TRAIN_MARINE.value not in pending
        ):
            candidates.append(
                _Candidate(
                    IntentType.TRAIN_MARINE,
                    60,
                    "barracks_idle",
                    mineral_cost=50,
                    supply_cost=1,
                )
            )

        if snapshot.marine_count >= self._config.attack_marine_threshold and (
            not snapshot.attack_started or snapshot.idle_marine_count > 0
        ):
            candidates.append(
                _Candidate(
                    IntentType.ATTACK_ENEMY_START,
                    50,
                    "marine_threshold_reached",
                )
            )

        selected: list[MacroIntent] = []
        available_minerals = snapshot.minerals
        available_supply = snapshot.supply_left
        seen: set[IntentType] = set()
        build_worker_reserved = False
        for candidate in sorted(candidates, key=lambda item: item.priority, reverse=True):
            if candidate.intent_type in seen:
                continue
            if candidate.uses_build_worker and build_worker_reserved:
                continue
            if candidate.mineral_cost > available_minerals:
                continue
            if candidate.supply_cost > available_supply:
                continue
            available_minerals -= candidate.mineral_cost
            available_supply -= candidate.supply_cost
            build_worker_reserved = build_worker_reserved or candidate.uses_build_worker
            seen.add(candidate.intent_type)
            selected.append(
                MacroIntent(
                    candidate.intent_type,
                    candidate.priority,
                    candidate.reason,
                    snapshot.game_loop,
                    (
                        {"reinforcement": snapshot.attack_started}
                        if candidate.intent_type is IntentType.ATTACK_ENEMY_START
                        else {}
                    ),
                )
            )

        if selected:
            return selected
        return [
            MacroIntent(
                IntentType.IDLE,
                0,
                "no_rule_triggered",
                snapshot.game_loop,
            )
        ]
