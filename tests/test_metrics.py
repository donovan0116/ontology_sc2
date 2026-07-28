from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.domain.records import ExecutionResult, ExecutionStatus
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
