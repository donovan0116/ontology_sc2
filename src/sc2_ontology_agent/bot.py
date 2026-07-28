from __future__ import annotations

from pathlib import Path

from sc2.bot_ai import BotAI
from sc2.data import Result
from sc2.ids.unit_typeid import UnitTypeId

from sc2_ontology_agent.config import BotConfig, GameConfig, LoggingConfig
from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.domain.records import ExecutionStatus
from sc2_ontology_agent.domain.state import GameSnapshot
from sc2_ontology_agent.execution.simple_executor import SimpleExecutor
from sc2_ontology_agent.logging.event_logger import EventLogger
from sc2_ontology_agent.logging.metrics import MetricsCollector, write_metrics
from sc2_ontology_agent.policy.protocol import TacticalAdvisor


class OntologySc2Bot(BotAI):
    """Thin BurnySc2 lifecycle adapter for the V0.1 domain and policy."""

    def __init__(
        self,
        *,
        bot_config: BotConfig,
        game_config: GameConfig,
        logging_config: LoggingConfig,
        advisor: TacticalAdvisor,
        event_logger: EventLogger,
        metrics: MetricsCollector,
        metrics_path: Path,
        replay_path: Path | None,
    ) -> None:
        super().__init__()
        self._bot_config = bot_config
        self._game_config = game_config
        self._logging_config = logging_config
        self._advisor = advisor
        self._event_logger = event_logger
        self._metrics = metrics
        self._metrics_path = metrics_path
        self._replay_path = replay_path
        self._executor = SimpleExecutor(self, bot_config)
        self._attack_started = False
        self._finalized = False
        self._final_metrics: dict[str, object] | None = None
        self._fatal_error: Exception | None = None

    @property
    def final_metrics(self) -> dict[str, object] | None:
        return self._final_metrics

    @property
    def fatal_error(self) -> Exception | None:
        return self._fatal_error

    async def on_start(self) -> None:
        try:
            self.client.game_step = self._game_config.game_step
            snapshot = self.create_snapshot()
            self._metrics.observe(snapshot)
            self._event_logger.log(
                "game_start",
                snapshot=snapshot,
                details={
                    "game_step": self._game_config.game_step,
                    "map_name": self._game_config.map_name,
                },
            )
        except Exception as error:
            self._remember_fatal_error(error)
            raise

    async def on_step(self, iteration: int) -> None:
        try:
            snapshot = self.create_snapshot()
            self._metrics.observe(snapshot)
            if iteration % self._logging_config.snapshot_interval_steps == 0:
                self._event_logger.log("snapshot", snapshot=snapshot)
            if iteration % self._bot_config.decision_interval_steps != 0:
                return
            intents = self._advisor.recommend(snapshot)
            for intent in intents:
                await self._execute_and_record(snapshot, intent)
        except Exception as error:
            self._remember_fatal_error(error)
            raise

    async def _execute_and_record(
        self,
        snapshot: GameSnapshot,
        intent: MacroIntent,
    ) -> None:
        self._metrics.record_intent(intent)
        self._event_logger.log(
            "rule_trigger",
            snapshot=snapshot,
            intent=intent,
        )
        execution = await self._executor.execute(intent)
        self._metrics.record_execution(execution)
        self._event_logger.log(
            "decision",
            snapshot=snapshot,
            intent=intent,
            execution=execution,
        )
        if (
            intent.intent_type is IntentType.ATTACK_ENEMY_START
            and execution.status is ExecutionStatus.ACCEPTED
            and not self._attack_started
        ):
            self._attack_started = True
            self._metrics.record_first_attack(snapshot.game_time_seconds)
            self._event_logger.log(
                "first_attack",
                snapshot=snapshot,
                intent=intent,
                execution=execution,
            )
        action_types = {
            IntentType.BUILD_SUPPLY,
            IntentType.BUILD_BARRACKS,
            IntentType.TRAIN_WORKER,
            IntentType.TRAIN_MARINE,
        }
        if intent.intent_type in action_types and execution.status in {
            ExecutionStatus.REJECTED,
            ExecutionStatus.FAILED,
        }:
            self._event_logger.log(
                "action_failure",
                snapshot=snapshot,
                intent=intent,
                execution=execution,
            )

    async def on_end(self, game_result: Result) -> None:
        if self._fatal_error is not None:
            message = f"{type(self._fatal_error).__name__}: {self._fatal_error}"
            self._event_logger.log(
                "game_end",
                snapshot=self._metrics.last_snapshot,
                details={"result": "Error", "upstream_result": game_result.name},
            )
            self._finalize(
                "Error",
                self._metrics.last_snapshot,
                message,
                force=True,
            )
            return
        try:
            snapshot = self.create_snapshot()
            self._metrics.observe(snapshot)
            self._event_logger.log(
                "game_end",
                snapshot=snapshot,
                details={"result": game_result.name},
            )
            self._finalize(game_result.name, snapshot, None)
        except Exception as error:
            self._remember_fatal_error(error)
            message = f"{type(error).__name__}: {error}"
            self._finalize(
                "Error",
                self._metrics.last_snapshot,
                message,
                force=True,
            )

    def finalize_exception(self, error: Exception) -> dict[str, object]:
        """Persist a failure if BurnySc2 exits before calling ``on_end``."""

        message = f"{type(error).__name__}: {error}"
        snapshot = self._metrics.last_snapshot
        self._event_logger.log(
            "exception",
            snapshot=snapshot,
            details={"exception_type": type(error).__name__, "message": str(error)},
        )
        return self._finalize("Error", snapshot, message, force=True)

    def _remember_fatal_error(self, error: Exception) -> None:
        if self._fatal_error is None:
            self._fatal_error = error
        self._event_logger.log(
            "exception",
            snapshot=self._metrics.last_snapshot,
            details={"exception_type": type(error).__name__, "message": str(error)},
        )

    def create_snapshot(self) -> GameSnapshot:
        depots = self.structures.of_type({UnitTypeId.SUPPLYDEPOT, UnitTypeId.SUPPLYDEPOTLOWERED})
        barracks = self.structures(UnitTypeId.BARRACKS)
        pending_actions: list[str] = []
        pending_types = (
            (UnitTypeId.SCV, IntentType.TRAIN_WORKER),
            (UnitTypeId.SUPPLYDEPOT, IntentType.BUILD_SUPPLY),
            (UnitTypeId.BARRACKS, IntentType.BUILD_BARRACKS),
            (UnitTypeId.MARINE, IntentType.TRAIN_MARINE),
        )
        for unit_type, intent_type in pending_types:
            if self.already_pending(unit_type) > 0:
                pending_actions.append(intent_type.value)
        return GameSnapshot(
            game_loop=int(self.state.game_loop),
            game_time_seconds=float(self.time),
            minerals=int(self.minerals),
            vespene=int(self.vespene),
            supply_used=float(self.supply_used),
            supply_cap=float(self.supply_cap),
            worker_count=self.workers.amount,
            marine_count=self.units(UnitTypeId.MARINE).amount,
            barracks_count=barracks.amount,
            supply_depot_count=depots.amount,
            enemy_units_visible=self.enemy_units.amount,
            enemy_structures_visible=self.enemy_structures.amount,
            pending_actions=tuple(pending_actions),
            idle_worker_count=self.workers.idle.amount,
            idle_marine_count=self.units(UnitTypeId.MARINE).idle.amount,
            pending_worker_count=int(self.already_pending(UnitTypeId.SCV)),
            pending_marine_count=int(self.already_pending(UnitTypeId.MARINE)),
            ready_supply_depot_count=depots.ready.amount,
            ready_barracks_count=barracks.ready.amount,
            idle_townhall_count=self.townhalls.ready.idle.amount,
            idle_barracks_count=barracks.ready.idle.amount,
            attack_started=self._attack_started,
        )

    def _finalize(
        self,
        result: str,
        snapshot: GameSnapshot | None,
        exception: str | None,
        *,
        force: bool = False,
    ) -> dict[str, object]:
        if self._finalized and self._final_metrics is not None and not force:
            return self._final_metrics
        replay_path = str(self._replay_path) if self._replay_path is not None else None
        self._final_metrics = self._metrics.finalize(
            result,
            snapshot,
            exception,
            replay_path,
        )
        write_metrics(self._final_metrics, self._metrics_path)
        self._finalized = True
        return self._final_metrics
