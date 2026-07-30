from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from executor_fakes import ExecutorFakeBot, FakeGroup, FakeTypedCollection, FakeUnit
from sc2.bot_ai import BotAI
from sc2.ids.unit_typeid import UnitTypeId
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
