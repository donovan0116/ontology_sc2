from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GameSnapshot:
    """Serializable game state presented to tactical advisors."""

    game_loop: int = 0
    game_time_seconds: float = 0.0
    minerals: int = 0
    vespene: int = 0
    supply_used: float = 0.0
    supply_cap: float = 0.0
    worker_count: int = 0
    marine_count: int = 0
    barracks_count: int = 0
    supply_depot_count: int = 0
    enemy_units_visible: int = 0
    enemy_structures_visible: int = 0
    pending_actions: tuple[str, ...] = ()
    idle_worker_count: int = 0
    idle_marine_count: int = 0
    pending_worker_count: int = 0
    pending_marine_count: int = 0
    ready_supply_depot_count: int = 0
    ready_barracks_count: int = 0
    idle_townhall_count: int = 0
    idle_barracks_count: int = 0
    attack_started: bool = False

    @property
    def supply_left(self) -> float:
        return self.supply_cap - self.supply_used

    @classmethod
    def empty(cls, **values: Any) -> GameSnapshot:
        """Create a mostly empty snapshot for tests and failure records."""

        return cls(**values)

    def to_dict(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}
