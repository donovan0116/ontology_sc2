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
    townhall_count: int = 0
    ready_townhall_count: int = 0
    orbital_count: int = 0
    refinery_count: int = 0
    ready_refinery_count: int = 0
    barracks_techlab_count: int = 0
    barracks_reactor_count: int = 0
    idle_barracks_techlab_count: int = 0
    idle_techlab_count: int = 0
    addonless_idle_barracks_count: int = 0
    marauder_count: int = 0
    idle_marauder_count: int = 0
    pending_marauder_count: int = 0
    army_supply: float = 0.0
    mineral_saturation_deficit: int = 0
    gas_saturation_deficit: int = 0
    enemy_combat_units_visible: int = 0
    enemy_units_near_base: int = 0
    stim_researched: bool = False
    stim_pending: bool = False

    @property
    def supply_left(self) -> float:
        return self.supply_cap - self.supply_used

    @classmethod
    def empty(cls, **values: Any) -> GameSnapshot:
        """Create a mostly empty snapshot for tests and failure records."""

        return cls(**values)

    def to_dict(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}
