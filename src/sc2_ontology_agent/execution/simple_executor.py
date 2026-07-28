from __future__ import annotations

from sc2.bot_ai import BotAI
from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2
from sc2.unit import Unit

from sc2_ontology_agent.config import BotConfig
from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.domain.records import ExecutionResult, ExecutionStatus


class SimpleExecutor:
    """Translate V0.1 macro intents into guarded BurnySc2 unit commands."""

    def __init__(self, bot: BotAI, config: BotConfig) -> None:
        self._bot = bot
        self._config = config

    async def execute(self, intent: MacroIntent) -> ExecutionResult:
        if intent.intent_type is IntentType.ATTACK_ENEMY_START:
            reinforcement = intent.parameters.get("reinforcement", False) is True
            return await self._attack_enemy_start(reinforcement)
        handlers = {
            IntentType.DISTRIBUTE_WORKERS: self._distribute_workers,
            IntentType.TRAIN_WORKER: self._train_worker,
            IntentType.BUILD_SUPPLY: self._build_supply,
            IntentType.BUILD_BARRACKS: self._build_barracks,
            IntentType.TRAIN_MARINE: self._train_marine,
            IntentType.IDLE: self._idle,
        }
        return await handlers[intent.intent_type]()

    async def _distribute_workers(self) -> ExecutionResult:
        if not self._bot.workers:
            return ExecutionResult(ExecutionStatus.REJECTED, "no_workers")
        if not self._bot.workers.idle:
            return ExecutionResult(ExecutionStatus.WAITING, "no_idle_workers")
        if not self._bot.townhalls.ready or not self._bot.mineral_field:
            return ExecutionResult(ExecutionStatus.REJECTED, "mining_prerequisite_missing")
        await self._bot.distribute_workers()
        return ExecutionResult(ExecutionStatus.ACCEPTED)

    async def _train_worker(self) -> ExecutionResult:
        if self._bot.supply_left < 1:
            return ExecutionResult(ExecutionStatus.WAITING, "supply_blocked")
        if not self._bot.townhalls.ready.idle:
            return ExecutionResult(ExecutionStatus.WAITING, "townhall_busy_or_unavailable")
        if not self._bot.can_afford(UnitTypeId.SCV):
            return ExecutionResult(ExecutionStatus.WAITING, "insufficient_resources")
        command = self._bot.townhalls.ready.idle.first.train(UnitTypeId.SCV)
        return self._command_result(command, "train_worker_command_rejected")

    async def _build_supply(self) -> ExecutionResult:
        return await self._build_structure(UnitTypeId.SUPPLYDEPOT)

    async def _build_barracks(self) -> ExecutionResult:
        depots = self._bot.structures.of_type(
            {UnitTypeId.SUPPLYDEPOT, UnitTypeId.SUPPLYDEPOTLOWERED}
        )
        if not depots.ready:
            return ExecutionResult(ExecutionStatus.REJECTED, "supply_depot_prerequisite_missing")
        return await self._build_structure(UnitTypeId.BARRACKS)

    async def _build_structure(self, unit_type: UnitTypeId) -> ExecutionResult:
        if not self._bot.can_afford(unit_type):
            return ExecutionResult(ExecutionStatus.WAITING, "insufficient_resources")
        if not self._bot.townhalls.ready:
            return ExecutionResult(ExecutionStatus.REJECTED, "no_ready_townhall")
        anchor = self._bot.townhalls.ready.first.position.towards(
            self._bot.game_info.map_center,
            self._config.building_spacing,
        )
        placement = await self._bot.find_placement(
            unit_type,
            near=anchor,
            max_distance=self._config.build_search_radius,
            random_alternative=False,
            placement_step=2,
        )
        if placement is None:
            return ExecutionResult(ExecutionStatus.FAILED, "build_placement_not_found")
        worker = self._bot.select_build_worker(placement)
        if worker is None:
            return ExecutionResult(ExecutionStatus.FAILED, "build_worker_not_found")
        command = worker.build(unit_type, placement)
        return self._command_result(command, "build_command_rejected")

    async def _train_marine(self) -> ExecutionResult:
        if self._bot.supply_left < 1:
            return ExecutionResult(ExecutionStatus.WAITING, "supply_blocked")
        barracks = self._bot.structures(UnitTypeId.BARRACKS).ready.idle
        if not barracks:
            return ExecutionResult(ExecutionStatus.WAITING, "barracks_busy_or_unavailable")
        if not self._bot.can_afford(UnitTypeId.MARINE):
            return ExecutionResult(ExecutionStatus.WAITING, "insufficient_resources")
        command = barracks.first.train(UnitTypeId.MARINE)
        return self._command_result(command, "train_marine_command_rejected")

    async def _attack_enemy_start(self, reinforcement: bool) -> ExecutionResult:
        all_marines = self._bot.units(UnitTypeId.MARINE)
        if not all_marines:
            return ExecutionResult(ExecutionStatus.REJECTED, "no_marines")
        marines = all_marines.idle if reinforcement else all_marines
        if not marines:
            return ExecutionResult(ExecutionStatus.WAITING, "no_idle_reinforcements")
        visible_structures = self._bot.enemy_structures.filter(lambda unit: unit.is_visible)
        target: Unit | Point2
        if visible_structures:
            target = visible_structures.closest_to(marines.center)
        elif self._bot.enemy_start_locations:
            target = self._bot.enemy_start_locations[0]
        else:
            return ExecutionResult(ExecutionStatus.FAILED, "enemy_start_location_unknown")
        issued = 0
        for marine in marines:
            if marine.attack(target) is not False:
                issued += 1
        if issued == 0:
            return ExecutionResult(ExecutionStatus.FAILED, "attack_commands_rejected")
        return ExecutionResult(ExecutionStatus.ACCEPTED)

    async def _idle(self) -> ExecutionResult:
        return ExecutionResult(ExecutionStatus.WAITING, "no_action")

    @staticmethod
    def _command_result(command: object, failure_reason: str) -> ExecutionResult:
        if command is False:
            return ExecutionResult(ExecutionStatus.FAILED, failure_reason)
        return ExecutionResult(ExecutionStatus.ACCEPTED)
