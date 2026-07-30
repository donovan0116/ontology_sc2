from __future__ import annotations

from pathlib import Path

from sc2.bot_ai import BotAI
from sc2.data import Result
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId

from sc2_ontology_agent.config import BotConfig, GameConfig, LoggingConfig
from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.domain.records import ExecutionStatus, StrategyEvent
from sc2_ontology_agent.domain.state import GameSnapshot
from sc2_ontology_agent.execution.simple_executor import SimpleExecutor
from sc2_ontology_agent.logging.event_logger import EventLogger
from sc2_ontology_agent.logging.metrics import MetricsCollector, write_metrics
from sc2_ontology_agent.policy.protocol import (
    ExecutionAwareAdvisor,
    TacticalAdvisor,
    TraceableAdvisor,
)


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
            self._drain_strategy_events()
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
        if isinstance(self._advisor, ExecutionAwareAdvisor):
            self._advisor.observe_execution(intent, execution)
            self._drain_strategy_events()
        if (
            intent.intent_type in {IntentType.ATTACK_ENEMY_START, IntentType.ATTACK_ENEMY}
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

    def _drain_strategy_events(self) -> None:
        if not isinstance(self._advisor, TraceableAdvisor):
            return
        for event in self._advisor.drain_events():
            self._record_strategy_event(event)

    def _record_strategy_event(self, event: StrategyEvent) -> None:
        self._event_logger.log(
            event.event_type,
            game_loop=event.game_loop,
            game_time_seconds=event.game_time_seconds,
            details=dict(event.details),
        )
        self._metrics.record_strategy_event(event)

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
        townhalls = self.structures.of_type(
            {
                UnitTypeId.COMMANDCENTER,
                UnitTypeId.ORBITALCOMMAND,
                UnitTypeId.PLANETARYFORTRESS,
            }
        )
        orbitals = self.structures(UnitTypeId.ORBITALCOMMAND)
        refineries = self.structures(UnitTypeId.REFINERY)
        techlabs = self.structures(UnitTypeId.BARRACKSTECHLAB)
        reactors = self.structures(UnitTypeId.BARRACKSREACTOR)
        marauders = self.units(UnitTypeId.MARAUDER)
        ready_townhalls = townhalls.ready
        techlab_tags = {techlab.tag for techlab in techlabs.ready}
        idle_barracks_techlab_count = barracks.ready.idle.filter(
            lambda structure: structure.add_on_tag in techlab_tags
        ).amount
        addonless_idle_barracks_count = barracks.ready.idle.filter(
            lambda structure: structure.add_on_tag == 0
        ).amount
        enemy_combat_units = self.enemy_units.filter(
            lambda unit: unit.is_visible and not getattr(unit, "is_worker", False)
        )
        enemy_units_near_base = enemy_combat_units.filter(
            lambda enemy: any(
                enemy.distance_to(townhall) <= self._bot_config.defense_radius
                for townhall in ready_townhalls
            )
        )
        stim_pending = self.already_pending_upgrade(UpgradeId.STIMPACK) > 0
        pending_actions: list[str] = []
        pending_types = (
            (UnitTypeId.SCV, IntentType.TRAIN_WORKER),
            (UnitTypeId.SUPPLYDEPOT, IntentType.BUILD_SUPPLY),
            (UnitTypeId.BARRACKS, IntentType.BUILD_BARRACKS),
            (UnitTypeId.REFINERY, IntentType.BUILD_REFINERY),
            (UnitTypeId.COMMANDCENTER, IntentType.EXPAND_COMMAND_CENTER),
            (UnitTypeId.ORBITALCOMMAND, IntentType.UPGRADE_ORBITAL),
            (UnitTypeId.BARRACKSTECHLAB, IntentType.BUILD_TECHLAB),
            (UnitTypeId.BARRACKSREACTOR, IntentType.BUILD_REACTOR),
            (UnitTypeId.MARINE, IntentType.TRAIN_MARINE),
            (UnitTypeId.MARAUDER, IntentType.TRAIN_MARAUDER),
        )
        for unit_type, intent_type in pending_types:
            if self.already_pending(unit_type) > 0:
                pending_actions.append(intent_type.value)
        if stim_pending:
            pending_actions.append(IntentType.RESEARCH_STIM.value)
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
            idle_townhall_count=ready_townhalls.idle.amount,
            idle_barracks_count=barracks.ready.idle.amount,
            attack_started=self._attack_started,
            townhall_count=townhalls.amount,
            ready_townhall_count=ready_townhalls.amount,
            orbital_count=orbitals.amount,
            refinery_count=refineries.amount,
            ready_refinery_count=refineries.ready.amount,
            barracks_techlab_count=techlabs.amount,
            barracks_reactor_count=reactors.amount,
            idle_barracks_techlab_count=idle_barracks_techlab_count,
            idle_techlab_count=techlabs.ready.idle.amount,
            addonless_idle_barracks_count=addonless_idle_barracks_count,
            marauder_count=marauders.amount,
            idle_marauder_count=marauders.idle.amount,
            pending_marauder_count=int(self.already_pending(UnitTypeId.MARAUDER)),
            army_supply=float(self.supply_army),
            mineral_saturation_deficit=sum(
                townhall.ideal_harvesters - townhall.assigned_harvesters
                for townhall in ready_townhalls
            ),
            gas_saturation_deficit=sum(
                refinery.ideal_harvesters - refinery.assigned_harvesters
                for refinery in refineries.ready
            ),
            enemy_combat_units_visible=enemy_combat_units.amount,
            enemy_units_near_base=enemy_units_near_base.amount,
            stim_researched=UpgradeId.STIMPACK in self.state.upgrades,
            stim_pending=stim_pending,
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
