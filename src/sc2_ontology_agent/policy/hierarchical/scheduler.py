"""Deterministic arbitration for hierarchical macro commands."""

from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.domain.state import GameSnapshot
from sc2_ontology_agent.policy.hierarchical.blackboard import StrategicBlackboard
from sc2_ontology_agent.policy.hierarchical.commands import CandidateIntent, ProducerKind

_EMERGENCY_PREEMPTED_INTENTS = frozenset(
    {
        IntentType.EXPAND_COMMAND_CENTER,
        IntentType.UPGRADE_ORBITAL,
        IntentType.BUILD_TECHLAB,
        IntentType.BUILD_REACTOR,
        IntentType.RESEARCH_STIM,
    }
)


class CommandScheduler:
    """Select compatible macro intents while reserving finite game resources."""

    def select(
        self,
        snapshot: GameSnapshot,
        candidates: list[CandidateIntent],
        blackboard: StrategicBlackboard,
    ) -> list[MacroIntent]:
        available_minerals = snapshot.minerals
        available_vespene = snapshot.vespene
        available_supply = snapshot.supply_left
        producer_capacity = {
            ProducerKind.TOWNHALL: snapshot.idle_townhall_count,
            ProducerKind.BARRACKS: snapshot.idle_barracks_count,
            ProducerKind.ADDONLESS_BARRACKS: snapshot.addonless_idle_barracks_count,
            ProducerKind.TECHLAB_BARRACKS: snapshot.idle_barracks_techlab_count,
            ProducerKind.TECHLAB: max(
                snapshot.idle_techlab_count,
                snapshot.idle_barracks_techlab_count,
            ),
        }
        selected: list[MacroIntent] = []
        worker_reserved = False
        seen: set[tuple[IntentType, str]] = set()
        ordered = sorted(
            enumerate(candidates),
            key=lambda item: (
                not item[1].emergency,
                -item[1].intent.priority,
                item[0],
            ),
        )
        emergency_present = any(candidate.emergency for candidate in candidates)

        for _, candidate in ordered:
            reason = self._suppression_reason(
                candidate,
                blackboard,
                snapshot,
                emergency_present,
                seen,
                worker_reserved,
                available_minerals,
                available_vespene,
                available_supply,
                producer_capacity,
            )
            if reason is not None:
                self._emit_suppressed(
                    blackboard,
                    candidate,
                    reason,
                    available_minerals,
                    available_vespene,
                    available_supply,
                )
                continue

            available_before_minerals = available_minerals
            available_before_vespene = available_vespene
            available_before_supply = available_supply
            selected.append(candidate.intent)
            seen.add((candidate.intent.intent_type, candidate.task_key))
            available_minerals -= candidate.mineral_cost
            available_vespene -= candidate.vespene_cost
            available_supply -= candidate.supply_cost
            worker_reserved = worker_reserved or candidate.uses_build_worker
            self._reserve_producer(candidate.producer, producer_capacity)
            attempts = (
                blackboard.mark_scheduled(candidate.task_key).attempts
                if candidate.task_key in blackboard.tasks
                else None
            )
            blackboard.emit(
                "command_scheduled",
                task_key=candidate.task_key,
                intent_type=candidate.intent.intent_type.value,
                priority=candidate.intent.priority,
                mineral_cost=candidate.mineral_cost,
                vespene_cost=candidate.vespene_cost,
                supply_cost=candidate.supply_cost,
                available_minerals=available_before_minerals,
                available_vespene=available_before_vespene,
                available_supply=available_before_supply,
                remaining_minerals=available_minerals,
                remaining_vespene=available_vespene,
                remaining_supply=available_supply,
                attempts=attempts,
            )

        if selected:
            return selected
        return [
            MacroIntent(
                IntentType.IDLE,
                0,
                "no_schedulable_commands",
                snapshot.game_loop,
                {"source_manager": "scheduler"},
            )
        ]

    @staticmethod
    def _suppression_reason(
        candidate: CandidateIntent,
        blackboard: StrategicBlackboard,
        snapshot: GameSnapshot,
        emergency_present: bool,
        seen: set[tuple[IntentType, str]],
        worker_reserved: bool,
        available_minerals: int,
        available_vespene: int,
        available_supply: float,
        producer_capacity: dict[ProducerKind, int],
    ) -> str | None:
        intent_type = candidate.intent.intent_type
        if (
            emergency_present
            and not candidate.emergency
            and intent_type in _EMERGENCY_PREEMPTED_INTENTS
        ):
            return "emergency_preempts_expansion_or_tech"
        if candidate.task_key in blackboard.tasks and not blackboard.is_schedulable(
            candidate.task_key
        ):
            return "task_not_schedulable"
        if (intent_type, candidate.task_key) in seen:
            return "duplicate_intent"
        if intent_type.value in snapshot.pending_actions:
            return "pending_action"
        if candidate.mineral_cost > available_minerals:
            return "insufficient_minerals"
        if candidate.vespene_cost > available_vespene:
            return "insufficient_vespene"
        if candidate.supply_cost > available_supply:
            return "insufficient_supply"
        if candidate.uses_build_worker and worker_reserved:
            return "build_worker_reserved"
        if candidate.producer is not None:
            producer_reason = CommandScheduler._producer_suppression_reason(
                candidate.producer,
                producer_capacity,
            )
            if producer_reason is not None:
                return producer_reason
        return None

    @staticmethod
    def _producer_suppression_reason(
        producer: ProducerKind,
        producer_capacity: dict[ProducerKind, int],
    ) -> str | None:
        if producer_capacity[producer] <= 0:
            return f"producer_unavailable:{producer.value}"
        if (
            producer
            in {
                ProducerKind.TECHLAB_BARRACKS,
                ProducerKind.ADDONLESS_BARRACKS,
            }
            and producer_capacity[ProducerKind.BARRACKS] <= 0
        ):
            return "producer_unavailable:barracks"
        return None

    @staticmethod
    def _reserve_producer(
        producer: ProducerKind | None,
        producer_capacity: dict[ProducerKind, int],
    ) -> None:
        if producer is None:
            return
        producer_capacity[producer] -= 1
        if producer in {
            ProducerKind.TECHLAB_BARRACKS,
            ProducerKind.ADDONLESS_BARRACKS,
        }:
            producer_capacity[ProducerKind.BARRACKS] -= 1

    @staticmethod
    def _emit_suppressed(
        blackboard: StrategicBlackboard,
        candidate: CandidateIntent,
        reason: str,
        available_minerals: int,
        available_vespene: int,
        available_supply: float,
    ) -> None:
        blackboard.emit(
            "command_suppressed",
            task_key=candidate.task_key,
            intent_type=candidate.intent.intent_type.value,
            priority=candidate.intent.priority,
            mineral_cost=candidate.mineral_cost,
            vespene_cost=candidate.vespene_cost,
            supply_cost=candidate.supply_cost,
            available_minerals=available_minerals,
            available_vespene=available_vespene,
            available_supply=available_supply,
            reason=reason,
            attempts=(
                blackboard.tasks[candidate.task_key].attempts
                if candidate.task_key in blackboard.tasks
                else None
            ),
        )
