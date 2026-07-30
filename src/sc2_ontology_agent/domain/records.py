from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

StrategyEventValue = str | int | float | bool | None


class ExecutionStatus(str, Enum):
    ACCEPTED = "accepted"
    WAITING = "waiting"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Outcome of translating one macro intent into an SC2 command."""

    status: ExecutionStatus
    reason: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {"status": self.status.value, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class StrategyEvent:
    event_type: str
    game_loop: int
    game_time_seconds: float
    details: dict[str, StrategyEventValue]
