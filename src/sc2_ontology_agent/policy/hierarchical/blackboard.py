from dataclasses import replace

from sc2_ontology_agent.config import BotConfig
from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.domain.records import (
    ExecutionResult,
    ExecutionStatus,
    StrategyEvent,
    StrategyEventValue,
)
from sc2_ontology_agent.domain.state import GameSnapshot
from sc2_ontology_agent.policy.hierarchical.commands import (
    CombatMode,
    ProductionGoal,
    ProductionPhase,
    ResourcePriority,
    TaskRecord,
    TaskState,
)


class StrategicBlackboard:
    """Serializable strategic state shared by hierarchical policy components."""

    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.snapshot = GameSnapshot.empty()
        self.production_phase = ProductionPhase.OPENING
        self.combat_mode = CombatMode.DEVELOP
        self.resource_priority = ResourcePriority.MINERALS
        self.production_goals: list[ProductionGoal] = []
        self.tasks: dict[str, TaskRecord] = {}
        self.scout_accepted = False
        self.attack_started = False
        self.mode_before_defense = CombatMode.DEVELOP
        self._events: list[StrategyEvent] = []

    def update(self, snapshot: GameSnapshot) -> None:
        self.snapshot = snapshot
        for key, record in tuple(self.tasks.items()):
            observed = getattr(snapshot, record.goal.completion_field)
            if (
                record.state is not TaskState.COMPLETED
                and observed >= record.goal.completion_target
            ):
                self._transition(key, TaskState.COMPLETED, "completion_fact_observed")
            elif (
                record.state is TaskState.ACCEPTED
                and record.accepted_time_seconds is not None
                and snapshot.game_time_seconds - record.accepted_time_seconds
                > self.config.task_timeout_seconds
            ):
                self._transition(key, TaskState.TIMED_OUT, "task_timeout")
                self.emit("strategy_replanned", task_key=key, reason="task_timeout")

    def ensure_task(self, goal: ProductionGoal) -> TaskRecord:
        if goal.key not in self.tasks:
            self.tasks[goal.key] = TaskRecord(
                goal=goal,
                last_transition_loop=self.snapshot.game_loop,
            )
            self.production_goals.append(goal)
        return self.tasks[goal.key]

    def is_schedulable(self, key: str) -> bool:
        record = self.tasks[key]
        if record.state in {TaskState.COMPLETED, TaskState.ACCEPTED}:
            return False
        return (
            self.snapshot.game_loop - record.last_transition_loop
            >= self.config.task_retry_cooldown_steps * self.config.decision_interval_steps
            if record.state is TaskState.WAITING
            else record.attempts <= self.config.task_retry_limit
        )

    def mark_scheduled(self, key: str) -> TaskRecord:
        record = self.tasks[key]
        self._transition(
            key,
            TaskState.SCHEDULED,
            None,
            attempts=record.attempts + 1,
            accepted_time_seconds=None,
        )
        return self.tasks[key]

    def observe_execution(
        self,
        intent: MacroIntent,
        result: ExecutionResult,
    ) -> TaskRecord | None:
        if (
            result.status is ExecutionStatus.ACCEPTED
            and intent.intent_type is IntentType.SCOUT_ENEMY_START
        ):
            self.scout_accepted = True

        task_key = intent.parameters.get("task_key")
        if not isinstance(task_key, str) or task_key not in self.tasks:
            return None

        state = TaskState(result.status.value)
        accepted_time_seconds = (
            self.snapshot.game_time_seconds if result.status is ExecutionStatus.ACCEPTED else None
        )
        self._transition(
            task_key,
            state,
            result.reason,
            accepted_time_seconds=accepted_time_seconds,
        )
        if result.status in {ExecutionStatus.FAILED, ExecutionStatus.REJECTED}:
            self._handle_exhausted_retries(task_key)
        return self.tasks[task_key]

    def _handle_exhausted_retries(self, key: str) -> None:
        record = self.tasks[key]
        if record.attempts <= self.config.task_retry_limit:
            return
        if record.goal.required and not record.replacement_used:
            self._transition(
                key,
                TaskState.PLANNED,
                "replacement_requested",
                attempts=0,
                replacement_used=True,
                accepted_time_seconds=None,
            )
            self.emit("strategy_replanned", task_key=key, reason="task_retry_exhausted")
            return
        self._transition(key, TaskState.FAILED, record.reason)

    def _transition(
        self,
        key: str,
        state: TaskState,
        reason: str | None,
        *,
        attempts: int | None = None,
        accepted_time_seconds: float | None = None,
        replacement_used: bool | None = None,
    ) -> None:
        previous = self.tasks[key]
        self.tasks[key] = replace(
            previous,
            state=state,
            reason=reason,
            last_transition_loop=self.snapshot.game_loop,
            attempts=previous.attempts if attempts is None else attempts,
            accepted_time_seconds=accepted_time_seconds,
            replacement_used=(
                previous.replacement_used if replacement_used is None else replacement_used
            ),
        )
        self.emit(
            "task_state_changed",
            task_key=key,
            previous_state=previous.state.value,
            state=state.value,
            reason=reason,
        )

    def emit(self, event_type: str, **details: StrategyEventValue) -> None:
        self._events.append(
            StrategyEvent(
                event_type=event_type,
                game_loop=self.snapshot.game_loop,
                game_time_seconds=self.snapshot.game_time_seconds,
                details=details,
            )
        )

    def drain_events(self) -> list[StrategyEvent]:
        events = self._events
        self._events = []
        return events
