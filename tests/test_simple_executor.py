from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from executor_fakes import ExecutorFakeBot, FakeGroup, FakeTypedCollection, FakeUnit
from sc2.bot_ai import BotAI
from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId
from sc2.position import Point2

from sc2_ontology_agent.config import BotConfig
from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.domain.records import ExecutionResult, ExecutionStatus
from sc2_ontology_agent.execution.simple_executor import SimpleExecutor


class FakeMarine:
    def __init__(self) -> None:
        self.targets: list[object] = []

    def attack(self, target: object) -> object:
        self.targets.append(target)
        return object()


class FakeMarines:
    def __init__(self, members: list[FakeMarine], idle: FakeMarines | None = None) -> None:
        self.members = members
        self._idle = idle
        self.center = object()

    @property
    def idle(self) -> FakeMarines:
        return self._idle or FakeMarines([])

    def __bool__(self) -> bool:
        return bool(self.members)

    def __iter__(self) -> Any:
        return iter(self.members)


class EmptyEnemyStructures:
    def filter(self, _predicate: object) -> EmptyEnemyStructures:
        return self

    def __bool__(self) -> bool:
        return False


class FakeAttackBot:
    def __init__(self, marines: FakeMarines, target: object) -> None:
        self._marines = marines
        self.enemy_structures = EmptyEnemyStructures()
        self.enemy_start_locations = [target]

    def units(self, _unit_type: object) -> FakeMarines:
        return self._marines


class FakeAvailability:
    def __init__(self, available: bool) -> None:
        self.available = available

    def __bool__(self) -> bool:
        return self.available

    @property
    def idle(self) -> FakeAvailability:
        return self

    @property
    def ready(self) -> FakeAvailability:
        return self


class FakeDistributionBot:
    def __init__(self) -> None:
        self.workers = FakeAvailability(True)
        self.townhalls = FakeAvailability(False)
        self.mineral_field = FakeAvailability(True)
        self.distribute_called = False

    async def distribute_workers(self) -> None:
        self.distribute_called = True


def attack_intent(*, reinforcement: bool) -> MacroIntent:
    return MacroIntent(
        IntentType.ATTACK_ENEMY_START,
        50,
        "threshold",
        100,
        {"reinforcement": reinforcement},
    )


def test_first_attack_commands_all_marines_even_when_only_one_is_idle() -> None:
    target = object()
    first = FakeMarine()
    second = FakeMarine()
    idle = FakeMarines([first])
    bot = FakeAttackBot(FakeMarines([first, second], idle), target)
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(attack_intent(reinforcement=False)))

    assert result.status is ExecutionStatus.ACCEPTED
    assert first.targets == [target]
    assert second.targets == [target]


def test_reinforcement_attack_commands_only_idle_marines() -> None:
    target = object()
    idle_marine = FakeMarine()
    busy_marine = FakeMarine()
    idle = FakeMarines([idle_marine])
    bot = FakeAttackBot(FakeMarines([idle_marine, busy_marine], idle), target)
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(attack_intent(reinforcement=True)))

    assert result.status is ExecutionStatus.ACCEPTED
    assert idle_marine.targets == [target]
    assert busy_marine.targets == []


def test_scout_moves_one_worker_to_enemy_start() -> None:
    bot = ExecutorFakeBot()
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(
        executor.execute(
            MacroIntent(
                IntentType.SCOUT_ENEMY_START,
                30,
                "scout_window",
                100,
            )
        )
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert bot.worker.moves == [bot.enemy_start]


def test_rally_moves_only_idle_bio_units_to_staging_point() -> None:
    bot = ExecutorFakeBot()
    home = FakeUnit(10, Point2((0, 0)))
    bot.townhalls = FakeGroup([home])
    bot.idle_marine = FakeUnit(50, Point2((1, 0)))
    bot.busy_marauder = FakeUnit(51, Point2((1, 1)), idle=False)
    bot.units = FakeTypedCollection(
        {
            UnitTypeId.MARINE: FakeGroup([bot.idle_marine]),
            UnitTypeId.MARAUDER: FakeGroup([bot.busy_marauder]),
        }
    )
    bot.expected_rally = Point2((35, 0))
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig(rally_map_fraction=0.35))

    result = asyncio.run(
        executor.execute(
            MacroIntent(
                IntentType.RALLY_ARMY,
                50,
                "muster",
                100,
            )
        )
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert bot.idle_marine.moves == [bot.expected_rally]
    assert bot.busy_marauder.moves == []


def test_defense_targets_enemy_closest_to_ready_townhall() -> None:
    bot = ExecutorFakeBot()
    home = FakeUnit(10, Point2((0, 0)))
    bot.townhalls = FakeGroup([home])
    bot.marine = FakeUnit(50, Point2((1, 0)))
    bot.units = FakeTypedCollection(
        {
            UnitTypeId.MARINE: FakeGroup([bot.marine]),
        }
    )
    bot.closest_threat = FakeUnit(70, Point2((5, 0)))
    far_threat = FakeUnit(71, Point2((20, 0)))
    bot.enemy_units = FakeGroup([far_threat, bot.closest_threat])
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(
        executor.execute(
            MacroIntent(
                IntentType.DEFEND_BASE,
                100,
                "base_threat",
                100,
            )
        )
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert bot.marine.targets == [bot.closest_threat]


def test_hierarchical_attack_uses_idle_reinforcements_after_first_wave() -> None:
    bot = ExecutorFakeBot()
    bot.idle_marine = FakeUnit(50, Point2((1, 0)))
    bot.busy_marauder = FakeUnit(51, Point2((1, 1)), idle=False)
    bot.units = FakeTypedCollection(
        {
            UnitTypeId.MARINE: FakeGroup([bot.idle_marine]),
            UnitTypeId.MARAUDER: FakeGroup([bot.busy_marauder]),
        }
    )
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(
        executor.execute(
            MacroIntent(
                IntentType.ATTACK_ENEMY,
                60,
                "reinforcement",
                100,
                {"reinforcement": True},
            )
        )
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert bot.idle_marine.targets == [bot.enemy_start]
    assert bot.busy_marauder.targets == []


def test_distribution_is_rejected_without_ready_townhall() -> None:
    bot = FakeDistributionBot()
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())
    intent = MacroIntent(
        IntentType.DISTRIBUTE_WORKERS,
        100,
        "idle_workers",
        1,
    )

    result = asyncio.run(executor.execute(intent))

    assert result.status is ExecutionStatus.REJECTED
    assert result.reason == "mining_prerequisite_missing"
    assert bot.distribute_called is False


@pytest.mark.parametrize(
    ("resource_priority", "resource_ratio"),
    [("gas", 1.5), ("minerals", 2.0)],
)
def test_distribution_uses_requested_resource_priority(
    resource_priority: str,
    resource_ratio: float,
) -> None:
    bot = ExecutorFakeBot()
    bot.townhalls = FakeGroup([FakeUnit(10, Point2((0, 0)))])
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(
        executor.execute(
            MacroIntent(
                IntentType.DISTRIBUTE_WORKERS,
                80,
                "worker_distribution_needed",
                100,
                {"resource_priority": resource_priority},
            )
        )
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert bot.distribution_ratios == [resource_ratio]


def priority_distribution_bot() -> tuple[ExecutorFakeBot, FakeUnit, FakeUnit, FakeUnit]:
    bot = ExecutorFakeBot()
    townhall = FakeUnit(10, Point2((0, 0)), surplus_harvesters=-1)
    refinery = FakeUnit(20, Point2((20, 0)), surplus_harvesters=-1)
    mineral_patch = FakeUnit(30, Point2((2, 0)))
    bot.townhalls = FakeGroup([townhall])
    bot.gas_buildings = FakeGroup([refinery])
    bot.mineral_field = FakeGroup([mineral_patch])
    return bot, bot.worker, refinery, mineral_patch


def test_gas_distribution_routes_eligible_worker_to_refinery_deficit() -> None:
    bot, worker, refinery, _ = priority_distribution_bot()
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(
        executor.execute(
            MacroIntent(
                IntentType.DISTRIBUTE_WORKERS,
                80,
                "gas_deficit",
                100,
                {"resource_priority": "gas"},
            )
        )
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert worker.gathers == [refinery]
    assert bot.distribution_ratios == []


def test_mineral_distribution_routes_eligible_worker_to_mineral_deficit() -> None:
    bot, worker, _, mineral_patch = priority_distribution_bot()
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(
        executor.execute(
            MacroIntent(
                IntentType.DISTRIBUTE_WORKERS,
                80,
                "mineral_deficit",
                100,
                {"resource_priority": "minerals"},
            )
        )
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert worker.gathers == [mineral_patch]
    assert bot.distribution_ratios == []


def test_build_refinery_selects_free_geyser_and_worker() -> None:
    bot = ExecutorFakeBot()
    bot.townhalls = FakeGroup([FakeUnit(10, Point2((0, 0)))])
    bot.geyser = FakeUnit(20, Point2((5, 0)))
    bot.vespene_geyser = FakeGroup([bot.geyser])
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(
        executor.execute(MacroIntent(IntentType.BUILD_REFINERY, 70, "first_refinery", 100))
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert bot.worker.builds == [(UnitTypeId.REFINERY, bot.geyser)]


def test_expand_fails_when_no_expansion_location_exists() -> None:
    bot = ExecutorFakeBot()
    bot.townhalls = FakeGroup([FakeUnit(10, Point2((0, 0)))])
    bot.next_expansion = None
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(
        executor.execute(MacroIntent(IntentType.EXPAND_COMMAND_CENTER, 40, "expansion", 100))
    )

    assert result == ExecutionResult(
        ExecutionStatus.FAILED,
        "expansion_location_not_found",
    )


@pytest.mark.parametrize(
    ("intent_type", "unit_type"),
    [
        (IntentType.BUILD_TECHLAB, UnitTypeId.BARRACKSTECHLAB),
        (IntentType.BUILD_REACTOR, UnitTypeId.BARRACKSREACTOR),
    ],
)
def test_addon_intent_uses_addonless_idle_barracks(
    intent_type: IntentType,
    unit_type: UnitTypeId,
) -> None:
    bot = ExecutorFakeBot()
    bot.barracks = FakeUnit(30, Point2((4, 0)), add_on_tag=0)
    bot.structures = FakeTypedCollection({UnitTypeId.BARRACKS: FakeGroup([bot.barracks])})
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(MacroIntent(intent_type, 50, "addon", 100)))

    assert result.status is ExecutionStatus.ACCEPTED
    assert bot.barracks.builds == [(unit_type, None)]


def test_orbital_upgrade_uses_idle_command_center() -> None:
    bot = ExecutorFakeBot()
    bot.command_center = FakeUnit(10, Point2((0, 0)))
    bot.structures = FakeTypedCollection(
        {
            UnitTypeId.COMMANDCENTER: FakeGroup([bot.command_center]),
        }
    )
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(
        executor.execute(
            MacroIntent(
                IntentType.UPGRADE_ORBITAL,
                70,
                "orbital",
                100,
            )
        )
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert bot.command_center.abilities == [AbilityId.UPGRADETOORBITAL_ORBITALCOMMAND]


def test_stim_research_uses_idle_techlab() -> None:
    bot = ExecutorFakeBot()
    bot.techlab = FakeUnit(40, Point2((6, 0)))
    bot.structures = FakeTypedCollection(
        {
            UnitTypeId.BARRACKSTECHLAB: FakeGroup([bot.techlab]),
        }
    )
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(
        executor.execute(
            MacroIntent(
                IntentType.RESEARCH_STIM,
                70,
                "stim",
                100,
            )
        )
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert bot.techlab.researched == [UpgradeId.STIMPACK]


def test_marauder_requires_idle_barracks_with_techlab() -> None:
    bot = ExecutorFakeBot()
    bot.structures = FakeTypedCollection(
        {
            UnitTypeId.BARRACKS: FakeGroup([FakeUnit(30, Point2((4, 0)))]),
            UnitTypeId.BARRACKSTECHLAB: FakeGroup(),
        }
    )
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(
        executor.execute(
            MacroIntent(
                IntentType.TRAIN_MARAUDER,
                60,
                "bio_ratio",
                100,
            )
        )
    )

    assert result == ExecutionResult(
        ExecutionStatus.REJECTED,
        "techlab_barracks_missing",
    )


def techlab_barracks_bot(
    *,
    barracks_idle: bool = True,
    command_result: object = True,
) -> tuple[ExecutorFakeBot, FakeUnit]:
    bot = ExecutorFakeBot()
    techlab = FakeUnit(40, Point2((6, 0)))
    barracks = FakeUnit(
        30,
        Point2((4, 0)),
        idle=barracks_idle,
        add_on_tag=techlab.tag,
        command_result=command_result,
    )
    bot.structures = FakeTypedCollection(
        {
            UnitTypeId.BARRACKS: FakeGroup([barracks]),
            UnitTypeId.BARRACKSTECHLAB: FakeGroup([techlab]),
        }
    )
    return bot, barracks


def marauder_intent() -> MacroIntent:
    return MacroIntent(IntentType.TRAIN_MARAUDER, 60, "bio_ratio", 100)


def stim_intent() -> MacroIntent:
    return MacroIntent(IntentType.RESEARCH_STIM, 70, "stim", 100)


def orbital_intent() -> MacroIntent:
    return MacroIntent(IntentType.UPGRADE_ORBITAL, 70, "orbital", 100)


def test_marauder_trains_from_matching_idle_techlab_barracks() -> None:
    bot, barracks = techlab_barracks_bot()
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(marauder_intent()))

    assert result.status is ExecutionStatus.ACCEPTED
    assert barracks.trained == [UnitTypeId.MARAUDER]


def test_marauder_waits_when_matching_techlab_barracks_is_busy() -> None:
    bot, barracks = techlab_barracks_bot(barracks_idle=False)
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(marauder_intent()))

    assert result == ExecutionResult(
        ExecutionStatus.WAITING,
        "techlab_barracks_busy_or_unavailable",
    )
    assert barracks.trained == []


@pytest.mark.parametrize("pending_progress", [0.5, 1.0])
def test_stim_research_rejects_pending_or_completed_upgrade(pending_progress: float) -> None:
    bot = ExecutorFakeBot()
    techlab = FakeUnit(40, Point2((6, 0)))
    bot.structures = FakeTypedCollection({UnitTypeId.BARRACKSTECHLAB: FakeGroup([techlab])})
    bot.pending_upgrades[UpgradeId.STIMPACK] = pending_progress
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(stim_intent()))

    assert result == ExecutionResult(ExecutionStatus.REJECTED, "stim_already_pending")
    assert techlab.researched == []


def test_orbital_upgrade_waits_for_resources() -> None:
    bot = ExecutorFakeBot()
    command_center = FakeUnit(10, Point2((0, 0)))
    bot.structures = FakeTypedCollection({UnitTypeId.COMMANDCENTER: FakeGroup([command_center])})
    bot.affordable = False
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(orbital_intent()))

    assert result == ExecutionResult(ExecutionStatus.WAITING, "insufficient_resources")
    assert command_center.abilities == []


def test_stim_research_waits_for_resources() -> None:
    bot = ExecutorFakeBot()
    techlab = FakeUnit(40, Point2((6, 0)))
    bot.structures = FakeTypedCollection({UnitTypeId.BARRACKSTECHLAB: FakeGroup([techlab])})
    bot.affordable = False
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(stim_intent()))

    assert result == ExecutionResult(ExecutionStatus.WAITING, "insufficient_resources")
    assert techlab.researched == []


def test_marauder_waits_when_supply_is_blocked() -> None:
    bot, barracks = techlab_barracks_bot()
    bot.supply_left = 1
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(marauder_intent()))

    assert result == ExecutionResult(ExecutionStatus.WAITING, "supply_blocked")
    assert barracks.trained == []


def test_marauder_waits_for_resources() -> None:
    bot, barracks = techlab_barracks_bot()
    bot.affordable = False
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(marauder_intent()))

    assert result == ExecutionResult(ExecutionStatus.WAITING, "insufficient_resources")
    assert barracks.trained == []


def test_orbital_upgrade_fails_when_command_is_rejected() -> None:
    bot = ExecutorFakeBot()
    command_center = FakeUnit(10, Point2((0, 0)), command_result=False)
    bot.structures = FakeTypedCollection({UnitTypeId.COMMANDCENTER: FakeGroup([command_center])})
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(orbital_intent()))

    assert result == ExecutionResult(ExecutionStatus.FAILED, "upgrade_orbital_command_rejected")
    assert command_center.abilities == [AbilityId.UPGRADETOORBITAL_ORBITALCOMMAND]


def test_stim_research_fails_when_command_is_rejected() -> None:
    bot = ExecutorFakeBot()
    techlab = FakeUnit(40, Point2((6, 0)), command_result=False)
    bot.structures = FakeTypedCollection({UnitTypeId.BARRACKSTECHLAB: FakeGroup([techlab])})
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(stim_intent()))

    assert result == ExecutionResult(ExecutionStatus.FAILED, "research_stim_command_rejected")
    assert techlab.researched == [UpgradeId.STIMPACK]


def test_marauder_training_fails_when_command_is_rejected() -> None:
    bot, barracks = techlab_barracks_bot(command_result=False)
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(marauder_intent()))

    assert result == ExecutionResult(ExecutionStatus.FAILED, "train_marauder_command_rejected")
    assert barracks.trained == [UnitTypeId.MARAUDER]
