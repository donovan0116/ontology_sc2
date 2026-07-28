from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

IntentParameter = str | int | float | bool | None


class IntentType(str, Enum):
    DISTRIBUTE_WORKERS = "DISTRIBUTE_WORKERS"
    TRAIN_WORKER = "TRAIN_WORKER"
    BUILD_SUPPLY = "BUILD_SUPPLY"
    BUILD_BARRACKS = "BUILD_BARRACKS"
    TRAIN_MARINE = "TRAIN_MARINE"
    ATTACK_ENEMY_START = "ATTACK_ENEMY_START"
    IDLE = "IDLE"


@dataclass(frozen=True, slots=True)
class MacroIntent:
    """A framework-independent high-level action request."""

    intent_type: IntentType
    priority: int
    reason: str
    created_at_game_loop: int
    parameters: dict[str, IntentParameter] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0 <= self.priority <= 100:
            raise ValueError("priority must be between 0 and 100")
        if not self.reason:
            raise ValueError("reason must not be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.intent_type.value,
            "priority": self.priority,
            "reason": self.reason,
            "created_at_game_loop": self.created_at_game_loop,
            "parameters": dict(self.parameters),
        }
