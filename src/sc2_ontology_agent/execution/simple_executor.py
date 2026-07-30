from __future__ import annotations

from sc2.bot_ai import BotAI
from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId
from sc2.position import Point2
from sc2.unit import Unit
from sc2.units import Units

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
        if intent.intent_type is IntentType.ATTACK_ENEMY:
            reinforcement = intent.parameters.get("reinforcement", False) is True
            return await self._attack_enemy(reinforcement)
        if intent.intent_type is IntentType.DISTRIBUTE_WORKERS:
            return await self._distribute_workers(intent.parameters.get("resource_priority"))
        handlers = {
            IntentType.TRAIN_WORKER: self._train_worker,
            IntentType.BUILD_SUPPLY: self._build_supply,
            IntentType.BUILD_BARRACKS: self._build_barracks,
            IntentType.BUILD_REFINERY: self._build_refinery,
            IntentType.EXPAND_COMMAND_CENTER: self._expand_command_center,
            IntentType.BUILD_TECHLAB: self._build_techlab,
            IntentType.BUILD_REACTOR: self._build_reactor,
            IntentType.UPGRADE_ORBITAL: self._upgrade_orbital,
            IntentType.RESEARCH_STIM: self._research_stim,
            IntentType.TRAIN_MARINE: self._train_marine,
            IntentType.TRAIN_MARAUDER: self._train_marauder,
            IntentType.SCOUT_ENEMY_START: self._scout_enemy_start,
            IntentType.RALLY_ARMY: self._rally_army,
            IntentType.DEFEND_BASE: self._defend_base,
            IntentType.IDLE: self._idle,
        }
        return await handlers[intent.intent_type]()

    async def _distribute_workers(self, resource_priority: object | None = None) -> ExecutionResult:
        if not self._bot.workers:
            return ExecutionResult(ExecutionStatus.REJECTED, "no_workers")
        if not self._bot.townhalls.ready or not self._bot.mineral_field:
            return ExecutionResult(ExecutionStatus.REJECTED, "mining_prerequisite_missing")
        workers = self._action_free_workers()
        if not workers:
            return ExecutionResult(ExecutionStatus.WAITING, "workers_already_commanded")
        idle_workers = workers.idle
        target = (
            self._priority_gather_target(resource_priority, idle_workers) if idle_workers else None
        )
        if target is not None:
            worker = idle_workers.closest_to(target)
            command = worker.gather(target)
            return self._command_result(command, "gather_command_rejected")
        commanded_worker_tags = self._worker_tags_received_action()
        if commanded_worker_tags:
            return ExecutionResult(ExecutionStatus.WAITING, "workers_already_commanded")
        if resource_priority == "gas":
            await self._bot.distribute_workers(resource_ratio=1.5)
        elif resource_priority == "minerals":
            await self._bot.distribute_workers(resource_ratio=2.0)
        else:
            await self._bot.distribute_workers()
        return ExecutionResult(ExecutionStatus.ACCEPTED)

    def _priority_gather_target(
        self,
        resource_priority: object,
        workers: Units,
    ) -> Unit | None:
        worker = workers.first
        if resource_priority == "gas":
            refineries = self._bot.gas_buildings.ready.filter(
                lambda refinery: refinery.surplus_harvesters < 0
            )
            return refineries.closest_to(worker) if refineries else None
        if resource_priority == "minerals":
            townhalls = self._bot.townhalls.ready.filter(
                lambda townhall: townhall.surplus_harvesters < 0
            )
            if not townhalls:
                return None
            mineral_fields = self._bot.mineral_field.filter(
                lambda mineral: any(mineral.distance_to(townhall) <= 8 for townhall in townhalls)
            )
            return mineral_fields.closest_to(worker) if mineral_fields else None
        return None

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
        if not depots:
            return ExecutionResult(ExecutionStatus.REJECTED, "supply_depot_prerequisite_missing")
        if not depots.ready:
            return ExecutionResult(ExecutionStatus.WAITING, "supply_depot_prerequisite_not_ready")
        return await self._build_structure(UnitTypeId.BARRACKS)

    async def _build_refinery(self) -> ExecutionResult:
        if not self._bot.townhalls.ready:
            return ExecutionResult(ExecutionStatus.REJECTED, "no_ready_townhall")
        townhall = self._bot.townhalls.ready.first
        geysers = self._bot.vespene_geyser.closer_than(15, townhall)
        available = geysers.filter(
            lambda geyser: not self._bot.gas_buildings.closer_than(1.0, geyser)
        )
        if not available:
            return ExecutionResult(ExecutionStatus.REJECTED, "no_free_geyser")
        return await self._build_at(UnitTypeId.REFINERY, available.closest_to(townhall))

    async def _expand_command_center(self) -> ExecutionResult:
        expansion = await self._bot.get_next_expansion()
        if expansion is None:
            return ExecutionResult(ExecutionStatus.FAILED, "expansion_location_not_found")
        return await self._build_at(UnitTypeId.COMMANDCENTER, expansion)

    async def _build_techlab(self) -> ExecutionResult:
        return self._build_addon(UnitTypeId.BARRACKSTECHLAB)

    async def _build_reactor(self) -> ExecutionResult:
        return self._build_addon(UnitTypeId.BARRACKSREACTOR)

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
        worker = self._select_worker(placement)
        if worker is None:
            return ExecutionResult(ExecutionStatus.FAILED, "build_worker_not_found")
        command = worker.build(unit_type, placement)
        return self._command_result(command, "build_command_rejected")

    async def _build_at(self, unit_type: UnitTypeId, location: Point2 | Unit) -> ExecutionResult:
        if not self._bot.can_afford(unit_type):
            return ExecutionResult(ExecutionStatus.WAITING, "insufficient_resources")
        worker = self._select_worker(location)
        if worker is None:
            return ExecutionResult(ExecutionStatus.FAILED, "build_worker_not_found")
        command = worker.build(unit_type, location)
        return self._command_result(command, "build_command_rejected")

    def _build_addon(self, unit_type: UnitTypeId) -> ExecutionResult:
        if not self._bot.can_afford(unit_type):
            return ExecutionResult(ExecutionStatus.WAITING, "insufficient_resources")
        barracks = self._bot.structures(UnitTypeId.BARRACKS).ready.idle.filter(
            lambda structure: structure.add_on_tag == 0
        )
        if not barracks:
            return ExecutionResult(ExecutionStatus.WAITING, "addonless_barracks_unavailable")
        command = barracks.first.build(unit_type)
        return self._command_result(command, "addon_command_rejected")

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

    async def _upgrade_orbital(self) -> ExecutionResult:
        command_centers = self._bot.structures(UnitTypeId.COMMANDCENTER)
        if not command_centers:
            return ExecutionResult(ExecutionStatus.REJECTED, "command_center_missing")
        idle_command_centers = command_centers.ready.idle
        if not idle_command_centers:
            return ExecutionResult(ExecutionStatus.WAITING, "command_center_busy_or_unavailable")
        if not self._bot.can_afford(UnitTypeId.ORBITALCOMMAND):
            return ExecutionResult(ExecutionStatus.WAITING, "insufficient_resources")
        command = idle_command_centers.first(AbilityId.UPGRADETOORBITAL_ORBITALCOMMAND)
        return self._command_result(command, "upgrade_orbital_command_rejected")

    async def _research_stim(self) -> ExecutionResult:
        if self._bot.already_pending_upgrade(UpgradeId.STIMPACK):
            return ExecutionResult(ExecutionStatus.REJECTED, "stim_already_pending")
        techlabs = self._bot.structures(UnitTypeId.BARRACKSTECHLAB)
        if not techlabs.ready:
            return ExecutionResult(ExecutionStatus.REJECTED, "techlab_missing")
        idle_techlabs = techlabs.ready.idle
        if not idle_techlabs:
            return ExecutionResult(ExecutionStatus.WAITING, "techlab_busy_or_unavailable")
        if not self._bot.can_afford(UpgradeId.STIMPACK):
            return ExecutionResult(ExecutionStatus.WAITING, "insufficient_resources")
        command = idle_techlabs.first.research(UpgradeId.STIMPACK)
        return self._command_result(command, "research_stim_command_rejected")

    async def _train_marauder(self) -> ExecutionResult:
        techlab_tags = {
            techlab.tag for techlab in self._bot.structures(UnitTypeId.BARRACKSTECHLAB).ready
        }
        ready_barracks = self._bot.structures(UnitTypeId.BARRACKS).ready
        techlab_barracks = ready_barracks.filter(
            lambda barracks: barracks.add_on_tag in techlab_tags
        )
        if not techlab_barracks:
            return ExecutionResult(ExecutionStatus.REJECTED, "techlab_barracks_missing")
        if self._bot.supply_left < 2:
            return ExecutionResult(ExecutionStatus.WAITING, "supply_blocked")
        idle_techlab_barracks = techlab_barracks.idle
        if not idle_techlab_barracks:
            return ExecutionResult(ExecutionStatus.WAITING, "techlab_barracks_busy_or_unavailable")
        if not self._bot.can_afford(UnitTypeId.MARAUDER):
            return ExecutionResult(ExecutionStatus.WAITING, "insufficient_resources")
        command = idle_techlab_barracks.first.train(UnitTypeId.MARAUDER)
        return self._command_result(command, "train_marauder_command_rejected")

    async def _scout_enemy_start(self) -> ExecutionResult:
        workers = self._action_free_workers().filter(
            lambda worker: not worker.is_carrying_minerals and not worker.is_carrying_vespene
        )
        if not workers:
            return ExecutionResult(ExecutionStatus.REJECTED, "no_scout_worker")
        if not self._bot.enemy_start_locations:
            return ExecutionResult(ExecutionStatus.FAILED, "enemy_start_location_unknown")
        idle_workers = workers.idle
        worker = idle_workers.first if idle_workers else workers.first
        command = worker.move(self._bot.enemy_start_locations[0])
        return self._command_result(command, "scout_command_rejected")

    async def _rally_army(self) -> ExecutionResult:
        if not self._bot.townhalls.ready:
            return ExecutionResult(ExecutionStatus.REJECTED, "no_ready_townhall")
        if not self._bot.enemy_start_locations:
            return ExecutionResult(ExecutionStatus.FAILED, "enemy_start_location_unknown")
        bio_units = self._bio_units().idle
        if not bio_units:
            return ExecutionResult(ExecutionStatus.WAITING, "no_idle_bio_units")
        home = self._bot.townhalls.ready.first
        enemy_start = self._bot.enemy_start_locations[0]
        rally = home.position.towards(
            enemy_start,
            home.distance_to(enemy_start) * self._config.rally_map_fraction,
        )
        issued = sum(unit.move(rally) is not False for unit in bio_units)
        if issued == 0:
            return ExecutionResult(ExecutionStatus.FAILED, "rally_commands_rejected")
        return ExecutionResult(ExecutionStatus.ACCEPTED)

    async def _defend_base(self) -> ExecutionResult:
        townhalls = self._bot.townhalls.ready
        if not townhalls:
            return ExecutionResult(ExecutionStatus.REJECTED, "no_ready_townhall")
        threats = self._bot.enemy_units.filter(
            lambda enemy: enemy.is_visible
            and any(
                enemy.distance_to(townhall) <= self._config.defense_radius for townhall in townhalls
            )
        )
        if not threats:
            return ExecutionResult(ExecutionStatus.WAITING, "no_visible_threats")
        bio_units = self._bio_units()
        if not bio_units:
            return ExecutionResult(ExecutionStatus.REJECTED, "no_bio_units")
        target = min(
            threats,
            key=lambda enemy: min(enemy.distance_to(townhall) for townhall in townhalls),
        )
        issued = sum(unit.attack(target) is not False for unit in bio_units)
        if issued == 0:
            return ExecutionResult(ExecutionStatus.FAILED, "defense_commands_rejected")
        return ExecutionResult(ExecutionStatus.ACCEPTED)

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

    async def _attack_enemy(self, reinforcement: bool) -> ExecutionResult:
        all_bio_units = self._bio_units()
        if not all_bio_units:
            return ExecutionResult(ExecutionStatus.REJECTED, "no_bio_units")
        bio_units = all_bio_units.idle if reinforcement else all_bio_units
        if not bio_units:
            return ExecutionResult(ExecutionStatus.WAITING, "no_idle_reinforcements")
        visible_structures = self._bot.enemy_structures.filter(lambda unit: unit.is_visible)
        target: Unit | Point2
        if visible_structures:
            target = visible_structures.closest_to(bio_units.center)
        elif self._bot.enemy_start_locations:
            target = self._bot.enemy_start_locations[0]
        else:
            return ExecutionResult(ExecutionStatus.FAILED, "enemy_start_location_unknown")
        issued = 0
        for unit in bio_units:
            if unit.attack(target) is not False:
                issued += 1
        if issued == 0:
            return ExecutionResult(ExecutionStatus.FAILED, "attack_commands_rejected")
        return ExecutionResult(ExecutionStatus.ACCEPTED)

    def _bio_units(self) -> Units:
        return self._bot.units.of_type({UnitTypeId.MARINE, UnitTypeId.MARAUDER})

    def _action_free_workers(self) -> Units:
        commanded_tags = self._worker_tags_received_action()
        return self._bot.workers.filter(lambda worker: worker.tag not in commanded_tags)

    def _worker_tags_received_action(self) -> set[int]:
        received_action: set[int] = set(getattr(self._bot, "unit_tags_received_action", set()))
        worker_tags = {worker.tag for worker in self._bot.workers}
        return worker_tags.intersection(received_action)

    def _select_worker(self, location: Point2 | Unit) -> Unit | None:
        selected = self._bot.select_build_worker(location)
        commanded_tags = self._worker_tags_received_action()
        if selected is not None and selected.tag not in commanded_tags:
            return selected
        workers = self._action_free_workers()
        if not workers:
            return None
        idle_workers = workers.idle
        return idle_workers.closest_to(location) if idle_workers else None

    async def _idle(self) -> ExecutionResult:
        return ExecutionResult(ExecutionStatus.WAITING, "no_action")

    @staticmethod
    def _command_result(command: object, failure_reason: str) -> ExecutionResult:
        if command is False:
            return ExecutionResult(ExecutionStatus.FAILED, failure_reason)
        return ExecutionResult(ExecutionStatus.ACCEPTED)
