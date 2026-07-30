from dataclasses import dataclass
from enum import Enum

from sc2_ontology_agent.domain.intent import IntentType, MacroIntent


class ProductionPhase(str, Enum):
    OPENING = "opening"
    EXPANSION = "expansion"
    TECH_UP = "tech_up"
    MUSTER = "muster"
    ATTACK = "attack"


class CombatMode(str, Enum):
    DEVELOP = "develop"
    RALLY = "rally"
    DEFEND = "defend"
    ATTACK = "attack"


class ResourcePriority(str, Enum):
    MINERALS = "minerals"
    GAS = "gas"


class TaskState(str, Enum):
    PLANNED = "planned"
    SCHEDULED = "scheduled"
    ACCEPTED = "accepted"
    WAITING = "waiting"
    REJECTED = "rejected"
    FAILED = "failed"
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"


class ProducerKind(str, Enum):
    TOWNHALL = "townhall"
    BARRACKS = "barracks"
    ADDONLESS_BARRACKS = "addonless_barracks"
    TECHLAB_BARRACKS = "techlab_barracks"
    TECHLAB = "techlab"


@dataclass(frozen=True, slots=True)
class ProductionGoal:
    key: str
    intent_type: IntentType
    completion_field: str
    completion_target: int | float | bool
    required: bool = True


@dataclass(frozen=True, slots=True)
class TaskRecord:
    goal: ProductionGoal
    state: TaskState = TaskState.PLANNED
    attempts: int = 0
    last_transition_loop: int = 0
    accepted_time_seconds: float | None = None
    reason: str | None = None
    replacement_used: bool = False


@dataclass(frozen=True, slots=True)
class CandidateIntent:
    intent: MacroIntent
    task_key: str
    mineral_cost: int = 0
    vespene_cost: int = 0
    supply_cost: float = 0.0
    uses_build_worker: bool = False
    producer: ProducerKind | None = None
    emergency: bool = False
