from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from sc2.ids.unit_typeid import UnitTypeId

from sc2_ontology_agent.bot import OntologySc2Bot
from sc2_ontology_agent.domain.intent import IntentType


class FakeGroup:
    def __init__(
        self,
        amount: int,
        *,
        idle_amount: int = 0,
        ready_amount: int | None = None,
        ready_idle_amount: int = 0,
    ) -> None:
        self.amount = amount
        self._idle_amount = idle_amount
        self._ready_amount = amount if ready_amount is None else ready_amount
        self._ready_idle_amount = ready_idle_amount

    @property
    def idle(self) -> FakeGroup:
        return FakeGroup(self._idle_amount)

    @property
    def ready(self) -> FakeGroup:
        return FakeGroup(self._ready_amount, idle_amount=self._ready_idle_amount)


class FakeStructures:
    def __init__(self, depots: FakeGroup, barracks: FakeGroup) -> None:
        self._depots = depots
        self._barracks = barracks

    def of_type(self, _types: set[UnitTypeId]) -> FakeGroup:
        return self._depots

    def __call__(self, _unit_type: UnitTypeId) -> FakeGroup:
        return self._barracks


class FakeSnapshotBot:
    def __init__(self) -> None:
        self.structures = FakeStructures(
            FakeGroup(2, ready_amount=1),
            FakeGroup(1, ready_amount=1, ready_idle_amount=1),
        )
        self.workers = FakeGroup(16, idle_amount=2)
        self._marines = FakeGroup(7, idle_amount=3)
        self.enemy_units = FakeGroup(4)
        self.enemy_structures = FakeGroup(1)
        self.townhalls = FakeGroup(1, ready_amount=1, ready_idle_amount=1)
        self.state = SimpleNamespace(game_loop=448)
        self.time = 20.0
        self.minerals = 250
        self.vespene = 0
        self.supply_used = 23
        self.supply_cap = 31
        self._attack_started = False

    def units(self, _unit_type: UnitTypeId) -> FakeGroup:
        return self._marines

    def already_pending(self, unit_type: UnitTypeId) -> float:
        return {
            UnitTypeId.SCV: 1.0,
            UnitTypeId.SUPPLYDEPOT: 0.0,
            UnitTypeId.BARRACKS: 1.0,
            UnitTypeId.MARINE: 1.0,
        }[unit_type]


def test_create_snapshot_exports_only_serializable_domain_values() -> None:
    bot = cast(Any, FakeSnapshotBot())

    snapshot = OntologySc2Bot.create_snapshot(bot)

    assert snapshot.game_loop == 448
    assert snapshot.worker_count == 16
    assert snapshot.idle_worker_count == 2
    assert snapshot.marine_count == 7
    assert snapshot.idle_marine_count == 3
    assert snapshot.ready_supply_depot_count == 1
    assert snapshot.ready_barracks_count == 1
    assert snapshot.idle_barracks_count == 1
    assert snapshot.pending_actions == (
        IntentType.TRAIN_WORKER.value,
        IntentType.BUILD_BARRACKS.value,
        IntentType.TRAIN_MARINE.value,
    )
    assert all(
        isinstance(value, int | float | bool | tuple) for value in snapshot.to_dict().values()
    )
