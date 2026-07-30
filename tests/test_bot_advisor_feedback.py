import asyncio
from pathlib import Path
from typing import cast

from sc2_ontology_agent.bot import OntologySc2Bot
from sc2_ontology_agent.config import BotConfig, GameConfig, LoggingConfig
from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.domain.records import ExecutionResult, ExecutionStatus, StrategyEvent
from sc2_ontology_agent.domain.state import GameSnapshot
from sc2_ontology_agent.logging.event_logger import EventLogger
from sc2_ontology_agent.logging.metrics import MetricsCollector


class FakeTraceableAdvisor:
    def __init__(self) -> None:
        self.feedback: list[tuple[MacroIntent, ExecutionResult]] = []
        self.events: list[StrategyEvent] = []

    def recommend(self, _snapshot: GameSnapshot) -> list[MacroIntent]:
        return []

    def observe_execution(self, intent: MacroIntent, result: ExecutionResult) -> None:
        self.feedback.append((intent, result))
        self.events.append(
            StrategyEvent(
                "task_state_changed",
                intent.created_at_game_loop,
                5.0,
                {"state": result.status.value},
            )
        )

    def drain_events(self) -> tuple[StrategyEvent, ...]:
        drained = tuple(self.events)
        self.events.clear()
        return drained


class RecordingEventLogger:
    def __init__(self) -> None:
        self.event_types: list[str] = []

    def log(self, event_type: str, **_values: object) -> None:
        self.event_types.append(event_type)


class AcceptedExecutor:
    async def execute(self, _intent: MacroIntent) -> ExecutionResult:
        return ExecutionResult(ExecutionStatus.ACCEPTED)


def make_bot(
    tmp_path: Path,
    *,
    advisor: FakeTraceableAdvisor,
    logger: RecordingEventLogger,
    metrics: MetricsCollector,
) -> OntologySc2Bot:
    return OntologySc2Bot(
        bot_config=BotConfig(),
        game_config=GameConfig(),
        logging_config=LoggingConfig(),
        advisor=advisor,
        event_logger=cast(EventLogger, logger),
        metrics=metrics,
        metrics_path=tmp_path / "metrics.json",
        replay_path=None,
    )


def test_bot_returns_execution_feedback_and_drains_strategy_events(tmp_path: Path) -> None:
    advisor = FakeTraceableAdvisor()
    logger = RecordingEventLogger()
    metrics = MetricsCollector("run-1")
    bot = make_bot(tmp_path, advisor=advisor, logger=logger, metrics=metrics)
    snapshot = GameSnapshot.empty(game_loop=100, game_time_seconds=5.0)
    intent = MacroIntent(IntentType.TRAIN_MARINE, 60, "test", 100)
    bot._executor = AcceptedExecutor()  # type: ignore[assignment]

    asyncio.run(bot._execute_and_record(snapshot, intent))

    assert advisor.feedback == [(intent, ExecutionResult(ExecutionStatus.ACCEPTED))]
    assert "task_state_changed" in logger.event_types
