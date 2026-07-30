from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId

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
        items: tuple[FakeUnit, ...] = (),
    ) -> None:
        self.amount = amount
        self._idle_amount = idle_amount
        self._ready_amount = amount if ready_amount is None else ready_amount
        self._ready_idle_amount = ready_idle_amount
        self._items = items

    @property
    def idle(self) -> FakeGroup:
        return FakeGroup(self._idle_amount, items=self._items)

    @property
    def ready(self) -> FakeGroup:
        return FakeGroup(
            self._ready_amount,
            idle_amount=self._ready_idle_amount,
            items=self._items,
        )

    def filter(self, predicate: Any) -> FakeGroup:
        matching = tuple(item for item in self._items if predicate(item))
        return FakeGroup(len(matching), items=matching)

    def __iter__(self) -> Any:
        return iter(self._items)


class FakeUnit:
    def __init__(
        self,
        *,
        add_on_tag: int = 0,
        tag: int = 0,
        visible: bool = True,
        worker: bool = False,
        nearby: bool = False,
        ideal_harvesters: int = 0,
        assigned_harvesters: int = 0,
    ) -> None:
        self.add_on_tag = add_on_tag
        self.tag = tag
        self.is_visible = visible
        self.is_worker = worker
        self._nearby = nearby
        self.ideal_harvesters = ideal_harvesters
        self.assigned_harvesters = assigned_harvesters

    def distance_to(self, _other: object) -> float:
        return 10.0 if self._nearby else 40.0


class FakeStructures:
    def __init__(
        self,
        depots: FakeGroup,
        barracks: FakeGroup,
        townhalls: FakeGroup,
        orbitals: FakeGroup,
        refineries: FakeGroup,
        techlabs: FakeGroup,
        reactors: FakeGroup,
    ) -> None:
        self._depots = depots
        self._barracks = barracks
        self._townhalls = townhalls
        self._orbitals = orbitals
        self._refineries = refineries
        self._techlabs = techlabs
        self._reactors = reactors

    def of_type(self, types: set[UnitTypeId]) -> FakeGroup:
        if UnitTypeId.SUPPLYDEPOT in types:
            return self._depots
        return self._townhalls

    def __call__(self, unit_type: UnitTypeId) -> FakeGroup:
        return {
            UnitTypeId.BARRACKS: self._barracks,
            UnitTypeId.ORBITALCOMMAND: self._orbitals,
            UnitTypeId.REFINERY: self._refineries,
            UnitTypeId.BARRACKSTECHLAB: self._techlabs,
            UnitTypeId.BARRACKSREACTOR: self._reactors,
        }[unit_type]


class FakeSnapshotBot:
    def __init__(self) -> None:
        self.structures = FakeStructures(
            FakeGroup(2, ready_amount=1),
            FakeGroup(
                2,
                ready_amount=2,
                ready_idle_amount=2,
                items=(FakeUnit(add_on_tag=11), FakeUnit()),
            ),
            FakeGroup(
                2,
                ready_amount=2,
                ready_idle_amount=1,
                items=(
                    FakeUnit(ideal_harvesters=16, assigned_harvesters=12),
                    FakeUnit(ideal_harvesters=16, assigned_harvesters=24),
                ),
            ),
            FakeGroup(1),
            FakeGroup(
                1,
                ready_amount=1,
                items=(FakeUnit(ideal_harvesters=3, assigned_harvesters=2),),
            ),
            FakeGroup(
                1,
                idle_amount=1,
                ready_amount=1,
                ready_idle_amount=1,
                items=(FakeUnit(tag=11),),
            ),
            FakeGroup(1),
        )
        self.workers = FakeGroup(16, idle_amount=2)
        self._marines = FakeGroup(7, idle_amount=3)
        self._marauders = FakeGroup(3, idle_amount=1)
        self.enemy_units = FakeGroup(
            4,
            items=(
                FakeUnit(nearby=True),
                FakeUnit(nearby=True),
                FakeUnit(nearby=False),
                FakeUnit(worker=True, nearby=True),
            ),
        )
        self.enemy_structures = FakeGroup(1)
        self.townhalls = self.structures.of_type(
            {UnitTypeId.COMMANDCENTER, UnitTypeId.ORBITALCOMMAND, UnitTypeId.PLANETARYFORTRESS}
        )
        self.state = SimpleNamespace(game_loop=448, upgrades={UpgradeId.STIMPACK})
        self.time = 20.0
        self.minerals = 250
        self.vespene = 0
        self.supply_used = 23
        self.supply_cap = 31
        self.supply_army = 13.0
        self._bot_config = SimpleNamespace(defense_radius=30)
        self._attack_started = False

    def units(self, unit_type: UnitTypeId) -> FakeGroup:
        return {UnitTypeId.MARINE: self._marines, UnitTypeId.MARAUDER: self._marauders}[unit_type]

    def already_pending(self, unit_type: UnitTypeId) -> float:
        pending = {
            UnitTypeId.SCV: 1.0,
            UnitTypeId.SUPPLYDEPOT: 0.0,
            UnitTypeId.BARRACKS: 1.0,
            UnitTypeId.REFINERY: 1.0,
            UnitTypeId.COMMANDCENTER: 1.0,
            UnitTypeId.ORBITALCOMMAND: 1.0,
            UnitTypeId.BARRACKSTECHLAB: 1.0,
            UnitTypeId.BARRACKSREACTOR: 1.0,
            UnitTypeId.MARINE: 1.0,
            UnitTypeId.MARAUDER: 1.0,
        }
        return pending[unit_type]

    def already_pending_upgrade(self, _upgrade_type: UpgradeId) -> float:
        return 1.0


def test_create_snapshot_exports_only_serializable_domain_values() -> None:
    bot = cast(Any, FakeSnapshotBot())

    snapshot = OntologySc2Bot.create_snapshot(bot)

    assert snapshot.game_loop == 448
    assert snapshot.worker_count == 16
    assert snapshot.idle_worker_count == 2
    assert snapshot.marine_count == 7
    assert snapshot.idle_marine_count == 3
    assert snapshot.ready_supply_depot_count == 1
    assert snapshot.ready_barracks_count == 2
    assert snapshot.idle_barracks_count == 2
    assert snapshot.pending_actions == (
        IntentType.TRAIN_WORKER.value,
        IntentType.BUILD_BARRACKS.value,
        IntentType.BUILD_REFINERY.value,
        IntentType.EXPAND_COMMAND_CENTER.value,
        IntentType.UPGRADE_ORBITAL.value,
        IntentType.BUILD_TECHLAB.value,
        IntentType.BUILD_REACTOR.value,
        IntentType.TRAIN_MARINE.value,
        IntentType.TRAIN_MARAUDER.value,
        IntentType.RESEARCH_STIM.value,
    )
    assert snapshot.townhall_count == 2
    assert snapshot.orbital_count == 1
    assert snapshot.refinery_count == 1
    assert snapshot.barracks_techlab_count == 1
    assert snapshot.barracks_reactor_count == 1
    assert snapshot.idle_barracks_techlab_count == 1
    assert snapshot.idle_techlab_count == 1
    assert snapshot.addonless_idle_barracks_count == 1
    assert snapshot.marauder_count == 3
    assert snapshot.idle_marauder_count == 1
    assert snapshot.pending_marauder_count == 1
    assert snapshot.army_supply == 13.0
    assert snapshot.mineral_saturation_deficit == -4
    assert snapshot.gas_saturation_deficit == 1
    assert snapshot.enemy_combat_units_visible == 3
    assert snapshot.enemy_units_near_base == 2
    assert snapshot.stim_researched is True
    assert snapshot.stim_pending is True
    assert all(
        isinstance(value, int | float | bool | tuple) for value in snapshot.to_dict().values()
    )
