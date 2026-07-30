from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from sc2_ontology_agent.domain.intent import MacroIntent
from sc2_ontology_agent.domain.records import ExecutionResult, ExecutionStatus, StrategyEvent
from sc2_ontology_agent.domain.state import GameSnapshot


class MetricsCollector:
    """Incrementally aggregates V0.1 metrics without retaining SC2 objects."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.peak_marine_count = 0
        self.supply_block_duration = 0.0
        self.intent_count_by_type: Counter[str] = Counter()
        self.accepted_action_count = 0
        self.rejected_action_count = 0
        self.failed_action_count = 0
        self.waiting_action_count = 0
        self.first_attack_time: float | None = None
        self.production_phase_reached: str | None = None
        self.first_scout_time_seconds: float | None = None
        self.first_expansion_time_seconds: float | None = None
        self.stim_completed_time_seconds: float | None = None
        self.first_defense_time_seconds: float | None = None
        self.task_failure_count = 0
        self.command_suppression_count = 0
        self._last_snapshot: GameSnapshot | None = None

    @property
    def last_snapshot(self) -> GameSnapshot | None:
        return self._last_snapshot

    def observe(self, snapshot: GameSnapshot) -> None:
        if (
            self._last_snapshot is not None
            and self._last_snapshot.supply_left <= 0
            and snapshot.game_time_seconds >= self._last_snapshot.game_time_seconds
        ):
            self.supply_block_duration += (
                snapshot.game_time_seconds - self._last_snapshot.game_time_seconds
            )
        self.peak_marine_count = max(self.peak_marine_count, snapshot.marine_count)
        self._last_snapshot = snapshot

    def record_intent(self, intent: MacroIntent) -> None:
        self.intent_count_by_type[intent.intent_type.value] += 1

    def record_execution(self, execution: ExecutionResult) -> None:
        if execution.status is ExecutionStatus.ACCEPTED:
            self.accepted_action_count += 1
        elif execution.status is ExecutionStatus.REJECTED:
            self.rejected_action_count += 1
        elif execution.status is ExecutionStatus.FAILED:
            self.failed_action_count += 1
        elif execution.status is ExecutionStatus.WAITING:
            self.waiting_action_count += 1

    def record_first_attack(self, game_time_seconds: float) -> None:
        if self.first_attack_time is None:
            self.first_attack_time = game_time_seconds

    def record_strategy_event(self, event: StrategyEvent) -> None:
        if event.event_type == "strategy_phase_changed":
            phase = event.details.get("phase")
            if isinstance(phase, str):
                self.production_phase_reached = phase
        elif event.event_type == "command_suppressed":
            self.command_suppression_count += 1
        elif event.event_type == "combat_mode_changed":
            if event.details.get("mode") == "defend" and self.first_defense_time_seconds is None:
                self.first_defense_time_seconds = event.game_time_seconds
        elif event.event_type == "task_state_changed":
            state = event.details.get("state")
            if state == "failed":
                self.task_failure_count += 1
            task_key = event.details.get("task_key")
            if (
                task_key == "research:stim"
                and state == "completed"
                and self.stim_completed_time_seconds is None
            ):
                self.stim_completed_time_seconds = event.game_time_seconds
            if state != "accepted":
                return
            if task_key == "scout:enemy_start" and self.first_scout_time_seconds is None:
                self.first_scout_time_seconds = event.game_time_seconds
            elif task_key == "build:expansion" and self.first_expansion_time_seconds is None:
                self.first_expansion_time_seconds = event.game_time_seconds

    def finalize(
        self,
        result: str,
        final_snapshot: GameSnapshot | None,
        exception: str | None,
        replay_path: str | None,
    ) -> dict[str, object]:
        snapshot = final_snapshot or self._last_snapshot or GameSnapshot.empty()
        return {
            "run_id": self.run_id,
            "result": result,
            "game_duration_seconds": snapshot.game_time_seconds,
            "final_game_loop": snapshot.game_loop,
            "final_worker_count": snapshot.worker_count,
            "final_marine_count": snapshot.marine_count,
            "peak_marine_count": self.peak_marine_count,
            "supply_block_duration": round(self.supply_block_duration, 3),
            "intent_count_by_type": dict(sorted(self.intent_count_by_type.items())),
            "accepted_action_count": self.accepted_action_count,
            "rejected_action_count": self.rejected_action_count,
            "failed_action_count": self.failed_action_count,
            "waiting_action_count": self.waiting_action_count,
            "first_attack_time": self.first_attack_time,
            "production_phase_reached": self.production_phase_reached,
            "first_scout_time_seconds": self.first_scout_time_seconds,
            "first_expansion_time_seconds": self.first_expansion_time_seconds,
            "stim_completed_time_seconds": self.stim_completed_time_seconds,
            "first_defense_time_seconds": self.first_defense_time_seconds,
            "task_failure_count": self.task_failure_count,
            "command_suppression_count": self.command_suppression_count,
            "exception": exception,
            "replay_path": replay_path,
        }


def write_metrics(metrics: dict[str, object], path: Path) -> None:
    """Atomically replace the per-game metrics document."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
