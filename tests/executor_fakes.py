from __future__ import annotations

from collections.abc import Callable, Iterable
from types import SimpleNamespace

from sc2.position import Point2


class FakeUnit:
    def __init__(
        self,
        tag: int,
        position: Point2,
        *,
        ready: bool = True,
        idle: bool = True,
        add_on_tag: int = 0,
        visible: bool = True,
    ) -> None:
        self.tag = tag
        self.position = position
        self.is_ready = ready
        self.is_idle = idle
        self.add_on_tag = add_on_tag
        self.is_visible = visible
        self.is_carrying_minerals = False
        self.is_carrying_vespene = False
        self.builds: list[tuple[object, object | None]] = []
        self.trained: list[object] = []
        self.researched: list[object] = []
        self.abilities: list[object] = []
        self.moves: list[object] = []
        self.targets: list[object] = []

    def build(self, unit_type: object, position: object | None = None) -> object:
        self.builds.append((unit_type, position))
        return object()

    def train(self, unit_type: object) -> object:
        self.trained.append(unit_type)
        return object()

    def research(self, upgrade: object) -> object:
        self.researched.append(upgrade)
        return object()

    def __call__(self, ability: object) -> object:
        self.abilities.append(ability)
        return object()

    def move(self, target: object) -> object:
        self.moves.append(target)
        return object()

    def attack(self, target: object) -> object:
        self.targets.append(target)
        return object()

    def distance_to(self, target: FakeUnit | Point2) -> float:
        point = target.position if isinstance(target, FakeUnit) else target
        return self.position.distance_to(point)


class FakeGroup:
    def __init__(self, members: Iterable[FakeUnit] = ()) -> None:
        self.members = list(members)

    def __iter__(self) -> Iterable[FakeUnit]:
        return iter(self.members)

    def __bool__(self) -> bool:
        return bool(self.members)

    @property
    def amount(self) -> int:
        return len(self.members)

    @property
    def first(self) -> FakeUnit:
        return self.members[0]

    @property
    def ready(self) -> FakeGroup:
        return FakeGroup(unit for unit in self.members if unit.is_ready)

    @property
    def idle(self) -> FakeGroup:
        return FakeGroup(unit for unit in self.members if unit.is_idle)

    @property
    def center(self) -> Point2:
        return self.first.position

    def filter(self, predicate: Callable[[FakeUnit], object]) -> FakeGroup:
        return FakeGroup(unit for unit in self.members if predicate(unit))

    def closer_than(self, distance: float, target: FakeUnit | Point2) -> FakeGroup:
        return FakeGroup(unit for unit in self.members if unit.distance_to(target) < distance)

    def closest_to(self, target: FakeUnit | Point2) -> FakeUnit:
        point = target.position if isinstance(target, FakeUnit) else target
        return min(self.members, key=lambda unit: unit.position.distance_to(point))


class FakeTypedCollection:
    def __init__(self, values: dict[object, FakeGroup] | None = None) -> None:
        self.values = values or {}

    def __call__(self, unit_type: object) -> FakeGroup:
        return self.values.get(unit_type, FakeGroup())

    def of_type(self, unit_types: set[object]) -> FakeGroup:
        members = [
            unit for unit_type in unit_types for unit in self.values.get(unit_type, FakeGroup())
        ]
        return FakeGroup(members)


class ExecutorFakeBot:
    def __init__(self) -> None:
        self.worker = FakeUnit(1, Point2((0, 0)))
        self.workers = FakeGroup([self.worker])
        self.townhalls = FakeGroup()
        self.vespene_geyser = FakeGroup()
        self.gas_buildings = FakeGroup()
        self.mineral_field = FakeGroup([FakeUnit(90, Point2((2, 0)))])
        self.structures = FakeTypedCollection()
        self.units = FakeTypedCollection()
        self.enemy_units = FakeGroup()
        self.enemy_structures = FakeGroup()
        self.enemy_start = Point2((100, 0))
        self.enemy_start_locations = [self.enemy_start]
        self.game_info = SimpleNamespace(map_center=Point2((50, 50)))
        self.next_expansion: Point2 | None = Point2((20, 0))
        self.distribution_ratios: list[float] = []

    def can_afford(self, _item: object) -> bool:
        return True

    def select_build_worker(self, _position: object) -> FakeUnit | None:
        return self.worker

    async def get_next_expansion(self) -> Point2 | None:
        return self.next_expansion

    async def distribute_workers(self, resource_ratio: float = 2) -> None:
        self.distribution_ratios.append(resource_ratio)
