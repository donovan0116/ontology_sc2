from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.domain.records import ExecutionResult, ExecutionStatus, StrategyEvent
from sc2_ontology_agent.domain.state import GameSnapshot
from sc2_ontology_agent.logging.metrics import MetricsCollector


def state(time: float, loop: int, marines: int, used: float, cap: float) -> GameSnapshot:
    return GameSnapshot.empty(
        game_loop=loop,
        game_time_seconds=time,
        marine_count=marines,
        worker_count=14,
        supply_used=used,
        supply_cap=cap,
    )


def test_metrics_aggregate_snapshots_intents_and_execution() -> None:
    collector = MetricsCollector("run-1")
    first = state(10.0, 224, 2, 15, 15)
    second = state(14.0, 314, 6, 15, 15)
    third = state(18.0, 403, 4, 15, 23)
    for item in (first, second, third):
        collector.observe(item)
    intent = MacroIntent(IntentType.TRAIN_MARINE, 40, "army_growth", 314)
    collector.record_intent(intent)
    collector.record_execution(ExecutionResult(ExecutionStatus.ACCEPTED))
    collector.record_execution(ExecutionResult(ExecutionStatus.FAILED, "no_worker"))
    collector.record_first_attack(14.0)

    metrics = collector.finalize("Victory", third, None, "replays/run-1.SC2Replay")

    assert metrics["peak_marine_count"] == 6
    assert metrics["supply_block_duration"] == 8.0
    assert metrics["intent_count_by_type"] == {"TRAIN_MARINE": 1}
    assert metrics["accepted_action_count"] == 1
    assert metrics["failed_action_count"] == 1
    assert metrics["first_attack_time"] == 14.0
    assert metrics["final_game_loop"] == 403


def test_strategy_events_add_optional_hierarchical_metrics() -> None:
    collector = MetricsCollector("run-1")
    collector.record_strategy_event(
        StrategyEvent(
            "strategy_phase_changed",
            90,
            9.0,
            {"phase": "opening"},
        )
    )
    collector.record_strategy_event(
        StrategyEvent(
            "strategy_phase_changed",
            100,
            10.0,
            {"phase": "expansion"},
        )
    )
    collector.record_strategy_event(
        StrategyEvent(
            "command_suppressed",
            110,
            11.0,
            {"reason": "insufficient_minerals"},
        )
    )
    collector.record_strategy_event(
        StrategyEvent(
            "task_state_changed",
            120,
            12.0,
            {"state": "failed"},
        )
    )
    collector.record_strategy_event(
        StrategyEvent(
            "task_state_changed",
            121,
            12.1,
            {"state": "failed"},
        )
    )
    collector.record_strategy_event(
        StrategyEvent(
            "command_suppressed",
            122,
            12.2,
            {"reason": "pending_action"},
        )
    )
    collector.record_strategy_event(
        StrategyEvent(
            "task_state_changed",
            130,
            13.0,
            {"task_key": "scout:enemy_start", "state": "accepted"},
        )
    )
    collector.record_strategy_event(
        StrategyEvent(
            "task_state_changed",
            140,
            14.0,
            {"task_key": "build:expansion", "state": "accepted"},
        )
    )
    collector.record_strategy_event(
        StrategyEvent(
            "task_state_changed",
            150,
            15.0,
            {"task_key": "research:stim", "state": "completed"},
        )
    )
    collector.record_strategy_event(
        StrategyEvent(
            "combat_mode_changed",
            160,
            16.0,
            {"mode": "defend"},
        )
    )
    collector.record_strategy_event(
        StrategyEvent(
            "task_state_changed",
            170,
            17.0,
            {"task_key": "scout:enemy_start", "state": "accepted"},
        )
    )
    collector.record_strategy_event(
        StrategyEvent(
            "task_state_changed",
            180,
            18.0,
            {"task_key": "build:expansion", "state": "accepted"},
        )
    )
    collector.record_strategy_event(
        StrategyEvent(
            "task_state_changed",
            190,
            19.0,
            {"task_key": "research:stim", "state": "completed"},
        )
    )
    collector.record_strategy_event(
        StrategyEvent(
            "combat_mode_changed",
            200,
            20.0,
            {"mode": "defend"},
        )
    )

    metrics = collector.finalize("Victory", GameSnapshot.empty(), None, None)

    assert metrics["production_phase_reached"] == "expansion"
    assert metrics["command_suppression_count"] == 2
    assert metrics["task_failure_count"] == 2
    assert metrics["first_scout_time_seconds"] == 13.0
    assert metrics["first_expansion_time_seconds"] == 14.0
    assert metrics["stim_completed_time_seconds"] == 15.0
    assert metrics["first_defense_time_seconds"] == 16.0


def test_hierarchical_metric_keys_have_stable_defaults() -> None:
    metrics = MetricsCollector("run-1").finalize("Victory", GameSnapshot.empty(), None, None)

    assert metrics["production_phase_reached"] is None
    assert metrics["first_scout_time_seconds"] is None
    assert metrics["first_expansion_time_seconds"] is None
    assert metrics["stim_completed_time_seconds"] is None
    assert metrics["first_defense_time_seconds"] is None
    assert metrics["task_failure_count"] == 0
    assert metrics["command_suppression_count"] == 0
