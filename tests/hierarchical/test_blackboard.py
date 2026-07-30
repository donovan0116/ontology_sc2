import pytest

from sc2_ontology_agent.config import BotConfig
from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.domain.records import ExecutionResult, ExecutionStatus
from sc2_ontology_agent.policy.hierarchical.blackboard import StrategicBlackboard
from sc2_ontology_agent.policy.hierarchical.commands import (
    ProductionGoal,
    TaskState,
)

from .conftest import make_snapshot


def test_accepted_build_task_completes_when_snapshot_reaches_target(
    blackboard: StrategicBlackboard,
) -> None:
    goal = ProductionGoal(
        key="build:first_barracks",
        intent_type=IntentType.BUILD_BARRACKS,
        completion_field="barracks_count",
        completion_target=1,
    )
    blackboard.ensure_task(goal)
    intent = MacroIntent(
        IntentType.BUILD_BARRACKS,
        70,
        "opening_goal",
        100,
        {"task_key": goal.key, "source_manager": "construction"},
    )
    blackboard.mark_scheduled(goal.key)
    blackboard.observe_execution(intent, ExecutionResult(ExecutionStatus.ACCEPTED))

    blackboard.update(make_snapshot(game_loop=120, barracks_count=1))

    assert blackboard.tasks[goal.key].state is TaskState.COMPLETED


def test_completed_task_does_not_emit_duplicate_completion_event(
    blackboard: StrategicBlackboard,
) -> None:
    goal = ProductionGoal(
        key="build:first_barracks",
        intent_type=IntentType.BUILD_BARRACKS,
        completion_field="barracks_count",
        completion_target=1,
    )
    blackboard.ensure_task(goal)

    blackboard.update(make_snapshot(game_loop=120, barracks_count=1))
    blackboard.drain_events()
    blackboard.update(make_snapshot(game_loop=124, barracks_count=1))

    assert not any(
        event.event_type == "task_state_changed" and event.details["task_key"] == goal.key
        for event in blackboard.drain_events()
    )


def test_waiting_task_honors_retry_cooldown(
    blackboard: StrategicBlackboard,
) -> None:
    goal = ProductionGoal(
        key="build:first_refinery",
        intent_type=IntentType.BUILD_REFINERY,
        completion_field="refinery_count",
        completion_target=1,
    )
    blackboard.ensure_task(goal)
    intent = MacroIntent(
        IntentType.BUILD_REFINERY,
        70,
        "opening_goal",
        100,
        {"task_key": goal.key, "source_manager": "construction"},
    )
    blackboard.mark_scheduled(goal.key)
    blackboard.observe_execution(
        intent,
        ExecutionResult(ExecutionStatus.WAITING, "insufficient_resources"),
    )

    assert blackboard.is_schedulable(goal.key) is False
    blackboard.update(make_snapshot(game_loop=104))
    assert blackboard.is_schedulable(goal.key) is False
    blackboard.update(make_snapshot(game_loop=108))
    assert blackboard.is_schedulable(goal.key) is True


def test_retry_cooldown_counts_recommendations_not_raw_game_loops() -> None:
    config = BotConfig(task_retry_cooldown_steps=2)
    blackboard = StrategicBlackboard(config)
    blackboard.update(make_snapshot(game_loop=100))
    goal = ProductionGoal(
        key="scout:enemy_start",
        intent_type=IntentType.SCOUT_ENEMY_START,
        completion_field=None,
        completion_target=True,
        required=False,
    )
    blackboard.ensure_task(goal, include_in_production_queue=False)
    intent = MacroIntent(
        goal.intent_type,
        50,
        "opening_scout",
        100,
        {"task_key": goal.key, "source_manager": "scout"},
    )
    blackboard.mark_scheduled(goal.key)
    blackboard.observe_execution(
        intent,
        ExecutionResult(ExecutionStatus.FAILED, "scout_command_rejected"),
    )

    blackboard.update(make_snapshot(game_loop=132))
    assert blackboard.is_schedulable(goal.key) is False

    blackboard.update(make_snapshot(game_loop=164))
    assert blackboard.is_schedulable(goal.key) is True


def test_accepted_task_times_out_and_emits_replan_event(
    bot_config: BotConfig,
) -> None:
    blackboard = StrategicBlackboard(bot_config)
    blackboard.update(make_snapshot(game_time_seconds=10.0))
    goal = ProductionGoal(
        key="build:expansion",
        intent_type=IntentType.EXPAND_COMMAND_CENTER,
        completion_field="townhall_count",
        completion_target=2,
    )
    blackboard.ensure_task(goal)
    intent = MacroIntent(
        goal.intent_type,
        40,
        "expansion_goal",
        100,
        {"task_key": goal.key, "source_manager": "construction"},
    )
    blackboard.mark_scheduled(goal.key)
    blackboard.observe_execution(intent, ExecutionResult(ExecutionStatus.ACCEPTED))

    blackboard.update(
        make_snapshot(
            game_loop=4000,
            game_time_seconds=131.0,
            townhall_count=1,
        )
    )

    assert blackboard.tasks[goal.key].state is TaskState.TIMED_OUT
    assert "strategy_replanned" in {event.event_type for event in blackboard.drain_events()}


def test_required_timeout_uses_replacement_then_terminal_exhaustion() -> None:
    config = BotConfig(
        task_retry_limit=0,
        task_retry_cooldown_steps=1,
        task_timeout_seconds=1,
    )
    blackboard = StrategicBlackboard(config)
    blackboard.update(make_snapshot())
    goal = ProductionGoal(
        key="build:expansion",
        intent_type=IntentType.EXPAND_COMMAND_CENTER,
        completion_field="townhall_count",
        completion_target=2,
    )
    blackboard.ensure_task(goal)
    intent = MacroIntent(
        goal.intent_type,
        40,
        "expansion_goal",
        100,
        {"task_key": goal.key, "source_manager": "construction"},
    )
    blackboard.mark_scheduled(goal.key)
    blackboard.observe_execution(intent, ExecutionResult(ExecutionStatus.ACCEPTED))

    blackboard.update(
        make_snapshot(
            game_loop=104,
            game_time_seconds=12.0,
            townhall_count=1,
        )
    )

    replacement = blackboard.tasks[goal.key]
    assert replacement.state is TaskState.PLANNED
    assert replacement.replacement_used is True
    assert replacement.attempts == 0
    assert blackboard.is_schedulable(goal.key) is True

    blackboard.mark_scheduled(goal.key)
    blackboard.observe_execution(intent, ExecutionResult(ExecutionStatus.ACCEPTED))
    blackboard.update(
        make_snapshot(
            game_loop=108,
            game_time_seconds=14.0,
            townhall_count=1,
        )
    )

    exhausted = blackboard.tasks[goal.key]
    assert exhausted.state is TaskState.FAILED
    assert blackboard.is_schedulable(goal.key) is False


def test_required_task_gets_one_replacement_before_permanent_failure() -> None:
    config = BotConfig(task_retry_limit=0)
    blackboard = StrategicBlackboard(config)
    blackboard.update(make_snapshot())
    goal = ProductionGoal(
        key="build:first_barracks",
        intent_type=IntentType.BUILD_BARRACKS,
        completion_field="barracks_count",
        completion_target=1,
    )
    blackboard.ensure_task(goal)
    intent = MacroIntent(
        goal.intent_type,
        70,
        "opening_goal",
        100,
        {"task_key": goal.key, "source_manager": "construction"},
    )

    blackboard.mark_scheduled(goal.key)
    blackboard.observe_execution(
        intent,
        ExecutionResult(ExecutionStatus.FAILED, "placement_not_found"),
    )
    assert blackboard.tasks[goal.key].replacement_used is True
    assert blackboard.is_schedulable(goal.key) is True

    blackboard.mark_scheduled(goal.key)
    blackboard.observe_execution(
        intent,
        ExecutionResult(ExecutionStatus.FAILED, "placement_not_found"),
    )
    assert blackboard.tasks[goal.key].state is TaskState.FAILED
    assert blackboard.is_schedulable(goal.key) is False


def test_accepted_scout_intent_marks_scout_as_accepted(
    blackboard: StrategicBlackboard,
) -> None:
    intent = MacroIntent(
        IntentType.SCOUT_ENEMY_START,
        60,
        "opening_scout",
        100,
    )

    blackboard.observe_execution(intent, ExecutionResult(ExecutionStatus.ACCEPTED))

    assert blackboard.scout_accepted is True


def test_mark_scheduled_rejects_duplicate_and_terminal_transitions(
    blackboard: StrategicBlackboard,
) -> None:
    goal = ProductionGoal(
        key="build:first_barracks",
        intent_type=IntentType.BUILD_BARRACKS,
        completion_field="barracks_count",
        completion_target=1,
    )
    blackboard.ensure_task(goal)
    blackboard.mark_scheduled(goal.key)

    with pytest.raises(ValueError, match="not schedulable"):
        blackboard.mark_scheduled(goal.key)

    blackboard.update(make_snapshot(game_loop=104, barracks_count=1))

    with pytest.raises(ValueError, match="not schedulable"):
        blackboard.mark_scheduled(goal.key)
