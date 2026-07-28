import json
from pathlib import Path

from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.domain.records import ExecutionResult, ExecutionStatus
from sc2_ontology_agent.domain.state import GameSnapshot
from sc2_ontology_agent.logging.event_logger import EventLogger


def test_jsonl_event_serializes_domain_values(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    logger = EventLogger(path, run_id="run-1", enabled=True)
    state = GameSnapshot.empty(game_loop=32, game_time_seconds=1.4)
    intent = MacroIntent(IntentType.BUILD_BARRACKS, 60, "production_capacity_missing", 32)

    logger.log(
        "decision",
        snapshot=state,
        intent=intent,
        execution=ExecutionResult(ExecutionStatus.ACCEPTED),
    )
    logger.close()

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["run_id"] == "run-1"
    assert record["game_loop"] == 32
    assert record["intent"]["type"] == "BUILD_BARRACKS"
    assert record["execution"]["status"] == "accepted"
    assert record["timestamp"].endswith("+00:00")


def test_disabled_logger_does_not_create_file(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    logger = EventLogger(path, run_id="run-1", enabled=False)
    logger.log("game_start")
    logger.close()
    assert not path.exists()
