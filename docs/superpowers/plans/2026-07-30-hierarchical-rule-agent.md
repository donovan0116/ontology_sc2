# Terran Hierarchical Rule Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the default flat Terran rule policy with a TStarBot2-inspired hierarchical rule agent that runs one two-base Marine/Marauder Stim timing strategy while preserving the `GameSnapshot -> TacticalAdvisor -> MacroIntent -> SimpleExecutor` boundary.

**Architecture:** A stateful `HierarchicalRulePolicy` owns a serializable strategic blackboard. Production and combat strategy controllers publish goals, six focused managers translate goals into candidate intents, and a scheduler resolves resource and facility conflicts before the existing executor receives intents. Optional advisor protocols feed execution results back into task state and drain framework-independent strategy events into the existing logger and metrics collector.

**Tech Stack:** Python 3.11, BurnySc2 7.3.0, frozen dataclasses and protocols, PyYAML, pytest, Ruff, mypy.

## Global Constraints

- Keep SC2 `Unit`, `Units`, tags, and `Point2` objects out of domain and policy models.
- Keep `TacticalAdvisor.recommend(snapshot: GameSnapshot) -> list[MacroIntent]` backward compatible.
- Keep `SimpleRulePolicy` selectable for regression and ablation runs.
- Put gameplay thresholds in typed YAML configuration; do not introduce policy magic numbers.
- Do not add RDF/OWL, reinforcement learning, Medivac, Siege Tank, air units, or advanced micro-management.
- Do not report integration success unless SC2 actually launches and produces results.
- Every production behavior starts with a failing test and follows red-green-refactor.
- Run `pytest`, `ruff check .`, `ruff format --check .`, and `mypy src` before completion.

---

## File Map

**Create**

- `src/sc2_ontology_agent/policy/factory.py`: construct the selected advisor.
- `src/sc2_ontology_agent/policy/hierarchical/__init__.py`: export the hierarchical advisor.
- `src/sc2_ontology_agent/policy/hierarchical/commands.py`: strategy enums, goals, tasks, and candidates.
- `src/sc2_ontology_agent/policy/hierarchical/blackboard.py`: stateful serializable blackboard and task lifecycle.
- `src/sc2_ontology_agent/policy/hierarchical/production_strategy.py`: two-base bio build-order controller.
- `src/sc2_ontology_agent/policy/hierarchical/combat_strategy.py`: develop/rally/defend/attack controller.
- `src/sc2_ontology_agent/policy/hierarchical/scheduler.py`: priority and resource arbitration.
- `src/sc2_ontology_agent/policy/hierarchical/advisor.py`: orchestration, feedback, and trace draining.
- `src/sc2_ontology_agent/policy/hierarchical/managers/__init__.py`: manager exports.
- `src/sc2_ontology_agent/policy/hierarchical/managers/economy.py`: worker production/distribution candidates.
- `src/sc2_ontology_agent/policy/hierarchical/managers/construction.py`: structure and addon candidates.
- `src/sc2_ontology_agent/policy/hierarchical/managers/production.py`: Marine/Marauder candidates.
- `src/sc2_ontology_agent/policy/hierarchical/managers/technology.py`: Orbital and Stim candidates.
- `src/sc2_ontology_agent/policy/hierarchical/managers/scout.py`: one-shot scout candidate.
- `src/sc2_ontology_agent/policy/hierarchical/managers/combat.py`: rally/defend/attack candidates.
- `tests/hierarchical/conftest.py`: shared snapshot and blackboard builders.
- `tests/hierarchical/test_blackboard.py`
- `tests/hierarchical/test_strategies.py`
- `tests/hierarchical/test_managers.py`
- `tests/hierarchical/test_scheduler.py`
- `tests/hierarchical/test_advisor.py`
- `tests/test_policy_factory.py`
- `tests/executor_fakes.py`: reusable BurnySc2-shaped fakes for executor tests.

**Modify**

- `src/sc2_ontology_agent/config.py`: hierarchical strategy configuration and validation.
- `src/sc2_ontology_agent/domain/intent.py`: new intent types.
- `src/sc2_ontology_agent/domain/records.py`: framework-independent strategy event record.
- `src/sc2_ontology_agent/domain/state.py`: hierarchical snapshot facts.
- `src/sc2_ontology_agent/policy/protocol.py`: optional feedback and trace protocols.
- `src/sc2_ontology_agent/execution/simple_executor.py`: execute economy, build, tech, scout, and combat intents.
- `src/sc2_ontology_agent/bot.py`: populate snapshot facts, deliver feedback, and drain strategy events.
- `src/sc2_ontology_agent/logging/metrics.py`: aggregate strategy milestones and counts.
- `src/sc2_ontology_agent/runner.py`: use the advisor factory.
- `configs/dev.yaml`
- `configs/batch.yaml`
- `README.md`
- `docs/architecture.md`
- `docs/experiment-data.md`
- `docs/roadmap.md`
- Existing tests under `tests/` where defaults or snapshot fakes change.

---

### Task 1: Configuration and Domain Surface

**Files:**

- Modify: `src/sc2_ontology_agent/config.py:34-43,138-154,214-272`
- Modify: `src/sc2_ontology_agent/domain/intent.py:9-16`
- Modify: `src/sc2_ontology_agent/domain/records.py`
- Modify: `src/sc2_ontology_agent/domain/state.py:7-32`
- Test: `tests/test_config.py`
- Test: `tests/test_simple_rule_policy.py`

**Interfaces:**

- Produces: `BotConfig.policy: str` and all hierarchical thresholds from the approved spec.
- Produces: new `IntentType` members used by managers and executor.
- Produces: `StrategyEvent`, shared without importing the hierarchical package from protocols.
- Produces: expanded `GameSnapshot` scalar facts used by all hierarchical modules.
- Preserves: `GameSnapshot.empty(**values)` and existing fields.

- [ ] **Step 1: Write failing configuration and domain tests**

Add these tests to `tests/test_config.py`:

```python
def test_hierarchical_config_defaults_are_complete(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}\n", encoding="utf-8")

    config = load_config(config_path)

    assert config.bot.policy == "hierarchical"
    assert config.bot.worker_limit == 44
    assert config.bot.max_barracks == 2
    assert config.bot.expansion_worker_threshold == 20
    assert config.bot.scout_start_time_seconds == 90
    assert config.bot.attack_army_supply == 24
    assert config.bot.reinforcement_army_supply == 8
    assert config.bot.marine_to_marauder_ratio == 2
    assert config.bot.defense_radius == 30
    assert config.bot.rally_map_fraction == 0.35
    assert config.bot.task_retry_limit == 3
    assert config.bot.task_retry_cooldown_steps == 2
    assert config.bot.task_timeout_seconds == 120


@pytest.mark.parametrize(
    "yaml_text, message",
    [
        ("bot:\n  policy: unknown\n", "policy"),
        ("bot:\n  policy: hierarchical\n  max_barracks: 1\n", "max_barracks"),
        ("bot:\n  rally_map_fraction: 0.0\n", "rally_map_fraction"),
        ("bot:\n  rally_map_fraction: 1.0\n", "rally_map_fraction"),
        ("bot:\n  task_retry_limit: -1\n", "task_retry_limit"),
    ],
)
def test_invalid_hierarchical_config_is_rejected(
    tmp_path: Path,
    yaml_text: str,
    message: str,
) -> None:
    config_path = tmp_path / "invalid-hierarchical.yaml"
    config_path.write_text(yaml_text, encoding="utf-8")

    with pytest.raises(ConfigError, match=message):
        load_config(config_path)


def test_simple_policy_allows_one_barracks(tmp_path: Path) -> None:
    config_path = tmp_path / "simple.yaml"
    config_path.write_text(
        "bot:\n  policy: simple\n  max_barracks: 1\n",
        encoding="utf-8",
    )

    assert load_config(config_path).bot.max_barracks == 1
```

Add to `tests/test_simple_rule_policy.py` and use this helper wherever the old V0.1 defaults are required:

```python
def simple_config(**changes: object) -> BotConfig:
    base = BotConfig(
        policy="simple",
        worker_limit=22,
        attack_marine_threshold=10,
        supply_buffer=4,
        max_barracks=1,
    )
    return replace(base, **changes)
```

Add a domain-surface assertion:

```python
def test_hierarchical_intents_and_snapshot_facts_are_available() -> None:
    state = GameSnapshot.empty(
        townhall_count=2,
        refinery_count=1,
        marauder_count=3,
        army_supply=14.0,
        stim_researched=True,
    )

    assert IntentType.RESEARCH_STIM.value == "RESEARCH_STIM"
    assert IntentType.DEFEND_BASE.value == "DEFEND_BASE"
    assert state.townhall_count == 2
    assert state.marauder_count == 3
    assert state.stim_researched is True
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
pytest tests/test_config.py tests/test_simple_rule_policy.py -v
```

Expected: failures for missing `BotConfig.policy`, hierarchical fields, new intent enum members, and new snapshot fields.

- [ ] **Step 3: Implement the configuration and domain fields**

Define `BotConfig` exactly as:

```python
@dataclass(frozen=True, slots=True)
class BotConfig:
    policy: str = "hierarchical"
    worker_limit: int = 44
    attack_marine_threshold: int = 10
    supply_buffer: int = 6
    max_barracks: int = 2
    decision_interval_steps: int = 4
    build_search_radius: int = 20
    building_spacing: int = 7
    expansion_worker_threshold: int = 20
    scout_start_time_seconds: int = 90
    attack_army_supply: int = 24
    reinforcement_army_supply: int = 8
    marine_to_marauder_ratio: int = 2
    defense_radius: int = 30
    rally_map_fraction: float = 0.35
    task_retry_limit: int = 3
    task_retry_cooldown_steps: int = 2
    task_timeout_seconds: int = 120
```

Extend `_typed()` with strict float handling:

```python
if expected is float and (
    not isinstance(value, int | float) or isinstance(value, bool)
):
    raise ConfigError(f"{key} must be a number")
```

Parse every field explicitly in `load_config()`. Validate:

```python
if bot.policy not in {"simple", "hierarchical"}:
    raise ConfigError(f"unsupported policy: {bot.policy}")
if bot.policy == "hierarchical" and bot.max_barracks < 2:
    raise ConfigError("max_barracks must be at least 2 for hierarchical policy")
if not 0.0 < bot.rally_map_fraction < 1.0:
    raise ConfigError("rally_map_fraction must be between 0 and 1")
```

Add these enum members to `IntentType`:

```python
BUILD_REFINERY = "BUILD_REFINERY"
EXPAND_COMMAND_CENTER = "EXPAND_COMMAND_CENTER"
UPGRADE_ORBITAL = "UPGRADE_ORBITAL"
BUILD_TECHLAB = "BUILD_TECHLAB"
BUILD_REACTOR = "BUILD_REACTOR"
RESEARCH_STIM = "RESEARCH_STIM"
TRAIN_MARAUDER = "TRAIN_MARAUDER"
SCOUT_ENEMY_START = "SCOUT_ENEMY_START"
RALLY_ARMY = "RALLY_ARMY"
DEFEND_BASE = "DEFEND_BASE"
ATTACK_ENEMY = "ATTACK_ENEMY"
```

Append these defaulted fields to `GameSnapshot`:

```python
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
```

Add to `domain/records.py`:

```python
StrategyEventValue = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class StrategyEvent:
    event_type: str
    game_loop: int
    game_time_seconds: float
    details: dict[str, StrategyEventValue]
```

- [ ] **Step 4: Run focused and regression tests**

Run:

```bash
pytest tests/test_config.py tests/test_simple_rule_policy.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sc2_ontology_agent/config.py src/sc2_ontology_agent/domain/intent.py \
  src/sc2_ontology_agent/domain/records.py src/sc2_ontology_agent/domain/state.py \
  tests/test_config.py tests/test_simple_rule_policy.py
git commit -m "feat: add hierarchical strategy domain configuration"
```

---

### Task 2: Blackboard Commands and Task Lifecycle

**Files:**

- Create: `src/sc2_ontology_agent/policy/hierarchical/__init__.py`
- Create: `src/sc2_ontology_agent/policy/hierarchical/commands.py`
- Create: `src/sc2_ontology_agent/policy/hierarchical/blackboard.py`
- Create: `tests/hierarchical/conftest.py`
- Create: `tests/hierarchical/test_blackboard.py`

**Interfaces:**

- Consumes: `BotConfig`, `IntentType`, `MacroIntent`, `ExecutionResult`, `GameSnapshot`.
- Produces: `ProductionPhase`, `CombatMode`, `ResourcePriority`, `TaskState`, `ProducerKind`.
- Produces: `ProductionGoal`, `TaskRecord`, and `CandidateIntent`.
- Produces: `StrategicBlackboard.update()`, `.ensure_task()`, `.mark_scheduled()`, `.observe_execution()`, `.drain_events()`.

- [ ] **Step 1: Write shared builders and failing lifecycle tests**

Create `tests/hierarchical/conftest.py`:

```python
from dataclasses import replace

import pytest

from sc2_ontology_agent.config import BotConfig
from sc2_ontology_agent.domain.state import GameSnapshot
from sc2_ontology_agent.policy.hierarchical.blackboard import StrategicBlackboard


@pytest.fixture
def bot_config() -> BotConfig:
    return BotConfig()


def make_snapshot(**changes: object) -> GameSnapshot:
    base = GameSnapshot.empty(
        game_loop=100,
        game_time_seconds=10.0,
        minerals=500,
        vespene=200,
        supply_used=12,
        supply_cap=23,
        worker_count=12,
        townhall_count=1,
        ready_townhall_count=1,
        idle_townhall_count=1,
    )
    return replace(base, **changes)


@pytest.fixture
def blackboard(bot_config: BotConfig) -> StrategicBlackboard:
    board = StrategicBlackboard(bot_config)
    board.update(make_snapshot())
    return board
```

Create `tests/hierarchical/test_blackboard.py`:

```python
from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.domain.records import ExecutionResult, ExecutionStatus
from sc2_ontology_agent.policy.hierarchical.blackboard import StrategicBlackboard
from sc2_ontology_agent.policy.hierarchical.commands import (
    ProductionGoal,
    TaskState,
)

from .conftest import make_snapshot


def test_accepted_build_task_completes_when_snapshot_reaches_target(
    blackboard: StrategicBlackboard,
) -> None:
    goal = ProductionGoal(
        key="build:first_barracks",
        intent_type=IntentType.BUILD_BARRACKS,
        completion_field="barracks_count",
        completion_target=1,
    )
    blackboard.ensure_task(goal)
    intent = MacroIntent(
        IntentType.BUILD_BARRACKS,
        70,
        "opening_goal",
        100,
        {"task_key": goal.key, "source_manager": "construction"},
    )
    blackboard.mark_scheduled(goal.key)
    blackboard.observe_execution(intent, ExecutionResult(ExecutionStatus.ACCEPTED))

    blackboard.update(make_snapshot(game_loop=120, barracks_count=1))

    assert blackboard.tasks[goal.key].state is TaskState.COMPLETED


def test_waiting_task_honors_retry_cooldown(
    blackboard: StrategicBlackboard,
) -> None:
    goal = ProductionGoal(
        key="build:first_refinery",
        intent_type=IntentType.BUILD_REFINERY,
        completion_field="refinery_count",
        completion_target=1,
    )
    blackboard.ensure_task(goal)
    intent = MacroIntent(
        IntentType.BUILD_REFINERY,
        70,
        "opening_goal",
        100,
        {"task_key": goal.key, "source_manager": "construction"},
    )
    blackboard.mark_scheduled(goal.key)
    blackboard.observe_execution(
        intent,
        ExecutionResult(ExecutionStatus.WAITING, "insufficient_resources"),
    )

    assert blackboard.is_schedulable(goal.key) is False
    blackboard.update(make_snapshot(game_loop=108))
    assert blackboard.is_schedulable(goal.key) is True


def test_accepted_task_times_out_and_emits_replan_event(
    bot_config: BotConfig,
) -> None:
    blackboard = StrategicBlackboard(bot_config)
    blackboard.update(make_snapshot(game_time_seconds=10.0))
    goal = ProductionGoal(
        key="build:expansion",
        intent_type=IntentType.EXPAND_COMMAND_CENTER,
        completion_field="townhall_count",
        completion_target=2,
    )
    blackboard.ensure_task(goal)
    intent = MacroIntent(
        goal.intent_type,
        40,
        "expansion_goal",
        100,
        {"task_key": goal.key, "source_manager": "construction"},
    )
    blackboard.mark_scheduled(goal.key)
    blackboard.observe_execution(intent, ExecutionResult(ExecutionStatus.ACCEPTED))

    blackboard.update(
        make_snapshot(
            game_loop=4000,
            game_time_seconds=131.0,
            townhall_count=1,
        )
    )

    assert blackboard.tasks[goal.key].state is TaskState.TIMED_OUT
    assert "strategy_replanned" in {
        event.event_type for event in blackboard.drain_events()
    }


def test_required_task_gets_one_replacement_before_permanent_failure() -> None:
    config = BotConfig(task_retry_limit=0)
    blackboard = StrategicBlackboard(config)
    blackboard.update(make_snapshot())
    goal = ProductionGoal(
        key="build:first_barracks",
        intent_type=IntentType.BUILD_BARRACKS,
        completion_field="barracks_count",
        completion_target=1,
    )
    blackboard.ensure_task(goal)
    intent = MacroIntent(
        goal.intent_type,
        70,
        "opening_goal",
        100,
        {"task_key": goal.key, "source_manager": "construction"},
    )

    blackboard.mark_scheduled(goal.key)
    blackboard.observe_execution(
        intent,
        ExecutionResult(ExecutionStatus.FAILED, "placement_not_found"),
    )
    assert blackboard.tasks[goal.key].replacement_used is True
    assert blackboard.is_schedulable(goal.key) is True

    blackboard.mark_scheduled(goal.key)
    blackboard.observe_execution(
        intent,
        ExecutionResult(ExecutionStatus.FAILED, "placement_not_found"),
    )
    assert blackboard.tasks[goal.key].state is TaskState.FAILED
    assert blackboard.is_schedulable(goal.key) is False
```

- [ ] **Step 2: Run the lifecycle tests and verify RED**

Run:

```bash
pytest tests/hierarchical/test_blackboard.py -v
```

Expected: import failure because the hierarchical command and blackboard modules do not exist.

- [ ] **Step 3: Implement command records**

Create `commands.py` with these public types:

```python
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


```

- [ ] **Step 4: Implement the blackboard**

Implement `StrategicBlackboard` with immutable `TaskRecord` replacement:

```python
class StrategicBlackboard:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.snapshot = GameSnapshot.empty()
        self.production_phase = ProductionPhase.OPENING
        self.combat_mode = CombatMode.DEVELOP
        self.resource_priority = ResourcePriority.MINERALS
        self.production_goals: list[ProductionGoal] = []
        self.tasks: dict[str, TaskRecord] = {}
        self.scout_accepted = False
        self.attack_started = False
        self.mode_before_defense = CombatMode.DEVELOP
        self._events: list[StrategyEvent] = []

    def update(self, snapshot: GameSnapshot) -> None:
        self.snapshot = snapshot
        for key, record in tuple(self.tasks.items()):
            observed = getattr(snapshot, record.goal.completion_field)
            if observed >= record.goal.completion_target:
                self._transition(key, TaskState.COMPLETED, "completion_fact_observed")
            elif (
                record.state is TaskState.ACCEPTED
                and record.accepted_time_seconds is not None
                and snapshot.game_time_seconds - record.accepted_time_seconds
                > self.config.task_timeout_seconds
            ):
                self._transition(key, TaskState.TIMED_OUT, "task_timeout")
                self.emit("strategy_replanned", task_key=key, reason="task_timeout")

    def ensure_task(self, goal: ProductionGoal) -> TaskRecord:
        if goal.key not in self.tasks:
            self.tasks[goal.key] = TaskRecord(
                goal=goal,
                last_transition_loop=self.snapshot.game_loop,
            )
        return self.tasks[goal.key]

    def is_schedulable(self, key: str) -> bool:
        record = self.tasks[key]
        if record.state in {TaskState.COMPLETED, TaskState.ACCEPTED}:
            return False
        return (
            self.snapshot.game_loop - record.last_transition_loop
            >= self.config.task_retry_cooldown_steps * self.config.decision_interval_steps
            if record.state is TaskState.WAITING
            else record.attempts <= self.config.task_retry_limit
        )
```

Implement `mark_scheduled()`, `observe_execution()`, `_transition()`, `emit()`, and
`drain_events()` using `dataclasses.replace`. Map `ExecutionStatus` to the same-named
`TaskState`, increment attempts on scheduling, set accepted time on accepted, set
`scout_accepted` for accepted scout intents, and include `task_state_changed` events. When a
required task exhausts its retry limit for the first time, reset it to `PLANNED`, set
`replacement_used=True`, reset attempts, and emit `strategy_replanned`; a second exhaustion is
permanent `FAILED`. Optional tasks become permanently failed after their first exhaustion.

- [ ] **Step 5: Run lifecycle tests**

Run:

```bash
pytest tests/hierarchical/test_blackboard.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/sc2_ontology_agent/policy/hierarchical \
  tests/hierarchical/conftest.py tests/hierarchical/test_blackboard.py
git commit -m "feat: add hierarchical strategy blackboard"
```

---

### Task 3: Production and Combat Strategy Controllers

**Files:**

- Create: `src/sc2_ontology_agent/policy/hierarchical/production_strategy.py`
- Create: `src/sc2_ontology_agent/policy/hierarchical/combat_strategy.py`
- Create: `tests/hierarchical/test_strategies.py`

**Interfaces:**

- Consumes: `StrategicBlackboard`.
- Produces: `ProductionStrategy.update(board) -> None`.
- Produces: `CombatStrategy.update(board) -> None`.
- Mutates only domain blackboard fields and event queue; emits no SC2 action.

- [ ] **Step 1: Write failing strategy transition tests**

Create `tests/hierarchical/test_strategies.py`:

```python
from sc2_ontology_agent.policy.hierarchical.blackboard import StrategicBlackboard
from sc2_ontology_agent.policy.hierarchical.combat_strategy import CombatStrategy
from sc2_ontology_agent.policy.hierarchical.commands import CandidateIntent
from sc2_ontology_agent.policy.hierarchical.commands import CombatMode, ProductionPhase
from sc2_ontology_agent.policy.hierarchical.production_strategy import ProductionStrategy

from .conftest import make_snapshot


def test_production_strategy_populates_approved_build_order(
    blackboard: StrategicBlackboard,
) -> None:
    ProductionStrategy().update(blackboard)

    assert [goal.key for goal in blackboard.production_goals] == [
        "build:first_depot",
        "build:first_barracks",
        "build:first_refinery",
        "upgrade:first_orbital",
        "build:expansion",
        "build:second_barracks",
        "build:first_techlab",
        "build:first_reactor",
        "research:stim",
    ]


def test_production_strategy_advances_all_phases(
    blackboard: StrategicBlackboard,
) -> None:
    strategy = ProductionStrategy()
    observations = [
        (make_snapshot(
            barracks_count=1,
            ready_barracks_count=1,
            refinery_count=1,
            ready_refinery_count=1,
            orbital_count=1,
        ), ProductionPhase.EXPANSION),
        (make_snapshot(
            barracks_count=2,
            ready_barracks_count=2,
            refinery_count=1,
            orbital_count=1,
            townhall_count=2,
            ready_townhall_count=2,
        ), ProductionPhase.TECH_UP),
        (make_snapshot(
            barracks_count=2,
            townhall_count=2,
            barracks_techlab_count=1,
            barracks_reactor_count=1,
            stim_researched=True,
        ), ProductionPhase.MUSTER),
        (make_snapshot(
            barracks_techlab_count=1,
            barracks_reactor_count=1,
            stim_researched=True,
            army_supply=24,
        ), ProductionPhase.ATTACK),
    ]
    for snapshot, expected in observations:
        blackboard.update(snapshot)
        strategy.update(blackboard)
        assert blackboard.production_phase is expected


def test_combat_strategy_defense_preempts_and_then_restores_rally(
    blackboard: StrategicBlackboard,
) -> None:
    strategy = CombatStrategy()
    blackboard.production_phase = ProductionPhase.MUSTER
    strategy.update(blackboard)
    assert blackboard.combat_mode is CombatMode.RALLY

    blackboard.update(make_snapshot(enemy_units_near_base=3))
    strategy.update(blackboard)
    assert blackboard.combat_mode is CombatMode.DEFEND

    blackboard.update(make_snapshot(game_loop=120, enemy_units_near_base=0))
    strategy.update(blackboard)
    assert blackboard.combat_mode is CombatMode.RALLY
```

- [ ] **Step 2: Run the strategy tests and verify RED**

Run:

```bash
pytest tests/hierarchical/test_strategies.py -v
```

Expected: import failures for the missing strategy controllers.

- [ ] **Step 3: Implement the production strategy**

Create a module-level immutable build order:

```python
BUILD_ORDER = (
    ProductionGoal("build:first_depot", IntentType.BUILD_SUPPLY, "supply_depot_count", 1),
    ProductionGoal("build:first_barracks", IntentType.BUILD_BARRACKS, "barracks_count", 1),
    ProductionGoal("build:first_refinery", IntentType.BUILD_REFINERY, "refinery_count", 1),
    ProductionGoal("upgrade:first_orbital", IntentType.UPGRADE_ORBITAL, "orbital_count", 1),
    ProductionGoal("build:expansion", IntentType.EXPAND_COMMAND_CENTER, "townhall_count", 2),
    ProductionGoal("build:second_barracks", IntentType.BUILD_BARRACKS, "barracks_count", 2),
    ProductionGoal("build:first_techlab", IntentType.BUILD_TECHLAB, "barracks_techlab_count", 1),
    ProductionGoal("build:first_reactor", IntentType.BUILD_REACTOR, "barracks_reactor_count", 1),
    ProductionGoal("research:stim", IntentType.RESEARCH_STIM, "stim_researched", True),
)
```

`ProductionStrategy.update()` must initialize goals once, ensure their tasks, derive the
furthest valid phase monotonically, switch resource priority to gas while a refinery is ready
and `vespene < 100`, then emit `strategy_phase_changed` only on a real change.

- [ ] **Step 4: Implement the combat strategy**

`CombatStrategy.update()` must:

```python
if snapshot.enemy_units_near_base > 0:
    if board.combat_mode is not CombatMode.DEFEND:
        board.mode_before_defense = board.combat_mode
        board.combat_mode = CombatMode.DEFEND
        board.emit("combat_mode_changed", mode="defend", reason="base_threat")
    return
if board.combat_mode is CombatMode.DEFEND:
    restored = board.mode_before_defense
    board.combat_mode = restored
    board.emit("combat_mode_changed", mode=restored.value, reason="threat_cleared")
    return
desired = {
    ProductionPhase.OPENING: CombatMode.DEVELOP,
    ProductionPhase.EXPANSION: CombatMode.DEVELOP,
    ProductionPhase.TECH_UP: CombatMode.DEVELOP,
    ProductionPhase.MUSTER: CombatMode.RALLY,
    ProductionPhase.ATTACK: CombatMode.ATTACK,
}[board.production_phase]
```

Assign and emit only when `desired` differs.

- [ ] **Step 5: Run strategy and blackboard tests**

Run:

```bash
pytest tests/hierarchical/test_blackboard.py tests/hierarchical/test_strategies.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/sc2_ontology_agent/policy/hierarchical/production_strategy.py \
  src/sc2_ontology_agent/policy/hierarchical/combat_strategy.py \
  tests/hierarchical/test_strategies.py
git commit -m "feat: add bio production and combat strategies"
```

---

### Task 4: Six Focused Managers

**Files:**

- Create: `src/sc2_ontology_agent/policy/hierarchical/managers/__init__.py`
- Create: `src/sc2_ontology_agent/policy/hierarchical/managers/economy.py`
- Create: `src/sc2_ontology_agent/policy/hierarchical/managers/construction.py`
- Create: `src/sc2_ontology_agent/policy/hierarchical/managers/production.py`
- Create: `src/sc2_ontology_agent/policy/hierarchical/managers/technology.py`
- Create: `src/sc2_ontology_agent/policy/hierarchical/managers/scout.py`
- Create: `src/sc2_ontology_agent/policy/hierarchical/managers/combat.py`
- Create: `tests/hierarchical/test_managers.py`

**Interfaces:**

- Each manager exposes `propose(board: StrategicBlackboard) -> list[CandidateIntent]`.
- Every hierarchical `MacroIntent.parameters` contains scalar `task_key` and `source_manager`.
- Costs: SCV 50/0/1, Depot 100/0/0, Barracks 150/0/0, Refinery 75/0/0,
  Command Center 400/0/0, Orbital 150/0/0, Tech Lab 50/25/0, Reactor 50/50/0,
  Stim 100/100/0, Marine 50/0/1, Marauder 100/25/2.

- [ ] **Step 1: Write parameterized failing manager tests**

Create `tests/hierarchical/test_managers.py`:

```python
import pytest

from sc2_ontology_agent.domain.intent import IntentType
from sc2_ontology_agent.policy.hierarchical.combat_strategy import CombatStrategy
from sc2_ontology_agent.policy.hierarchical.managers.combat import CombatManager
from sc2_ontology_agent.policy.hierarchical.managers.construction import ConstructionManager
from sc2_ontology_agent.policy.hierarchical.managers.economy import EconomyManager
from sc2_ontology_agent.policy.hierarchical.managers.production import ProductionManager
from sc2_ontology_agent.policy.hierarchical.managers.scout import ScoutManager
from sc2_ontology_agent.policy.hierarchical.managers.technology import TechnologyManager
from sc2_ontology_agent.policy.hierarchical.production_strategy import ProductionStrategy

from .conftest import make_snapshot


def types(candidates: list[CandidateIntent]) -> list[IntentType]:
    return [candidate.intent.intent_type for candidate in candidates]


def test_economy_proposes_worker_and_gas_biased_distribution(blackboard) -> None:
    blackboard.update(make_snapshot(
        worker_count=20,
        idle_worker_count=1,
        idle_townhall_count=1,
        ready_refinery_count=1,
        gas_saturation_deficit=3,
        vespene=0,
    ))

    candidates = EconomyManager().propose(blackboard)

    assert types(candidates) == [
        IntentType.DISTRIBUTE_WORKERS,
        IntentType.TRAIN_WORKER,
    ]
    assert candidates[0].intent.parameters["resource_priority"] == "gas"


def test_construction_proposes_only_first_incomplete_build_goal(blackboard) -> None:
    ProductionStrategy().update(blackboard)
    blackboard.update(make_snapshot(supply_depot_count=1))

    candidates = ConstructionManager().propose(blackboard)

    assert types(candidates) == [IntentType.BUILD_BARRACKS]
    assert candidates[0].task_key == "build:first_barracks"


@pytest.mark.parametrize(
    "marine_count,marauder_count,expected",
    [
        (2, 1, IntentType.TRAIN_MARINE),
        (4, 1, IntentType.TRAIN_MARAUDER),
    ],
)
def test_production_maintains_two_to_one_ratio(
    blackboard,
    marine_count: int,
    marauder_count: int,
    expected: IntentType,
) -> None:
    blackboard.update(make_snapshot(
        ready_barracks_count=2,
        idle_barracks_count=2,
        idle_barracks_techlab_count=1,
        marine_count=marine_count,
        marauder_count=marauder_count,
        supply_cap=100,
    ))

    assert types(ProductionManager().propose(blackboard))[0] is expected


def test_technology_proposes_stim_when_techlab_is_ready(blackboard) -> None:
    ProductionStrategy().update(blackboard)
    blackboard.update(make_snapshot(
        supply_depot_count=1,
        barracks_count=2,
        refinery_count=1,
        orbital_count=1,
        townhall_count=2,
        barracks_techlab_count=1,
        barracks_reactor_count=1,
        idle_barracks_techlab_count=1,
        stim_researched=False,
        stim_pending=False,
    ))

    assert types(TechnologyManager().propose(blackboard)) == [IntentType.RESEARCH_STIM]


def test_scout_is_one_shot_after_time_window(blackboard) -> None:
    blackboard.update(make_snapshot(game_time_seconds=90.0))

    candidates = ScoutManager().propose(blackboard)
    blackboard.scout_accepted = True

    assert types(candidates) == [IntentType.SCOUT_ENEMY_START]
    assert ScoutManager().propose(blackboard) == []


def test_combat_defense_has_emergency_candidate(blackboard) -> None:
    blackboard.update(make_snapshot(enemy_units_near_base=2, marine_count=4))
    CombatStrategy().update(blackboard)

    candidate = CombatManager().propose(blackboard)[0]

    assert candidate.intent.intent_type is IntentType.DEFEND_BASE
    assert candidate.emergency is True
```

- [ ] **Step 2: Run manager tests and verify RED**

Run:

```bash
pytest tests/hierarchical/test_managers.py -v
```

Expected: import failures for missing manager modules.

- [ ] **Step 3: Implement the manager modules**

Use one private helper in `managers/__init__.py` to create an intent without duplicating
parameter assembly:

```python
def candidate(
    board: StrategicBlackboard,
    intent_type: IntentType,
    priority: int,
    reason: str,
    task_key: str,
    source_manager: str,
    **costs: object,
) -> CandidateIntent:
    intent = MacroIntent(
        intent_type,
        priority,
        reason,
        board.snapshot.game_loop,
        {"task_key": task_key, "source_manager": source_manager},
    )
    return CandidateIntent(intent=intent, task_key=task_key, **costs)
```

Implement these manager rules:

- Economy: distribute when idle or either saturation deficit is non-zero; train SCV below
  `worker_limit` when a townhall is idle.
- Construction and Technology both inspect the same queue head:

  ```python
  current = next(
      (
          goal
          for goal in board.production_goals
          if board.tasks[goal.key].state is not TaskState.COMPLETED
      ),
      None,
  )
  ```

  Construction proposes it only when its type is Depot, Barracks, Refinery, Command Center,
  Tech Lab, or Reactor. Technology proposes it only when its type is Orbital or Stim. A manager
  returns no queued-goal candidate when the head belongs to the other manager, preserving the
  build order. Construction additionally proposes a reactive Depot at priority 90 when
  `supply_left <= supply_buffer` and no Depot is pending.
- Production: after a ready Barracks exists, select Marauder when
  `marine_count > marauder_count * marine_to_marauder_ratio`; otherwise Marine.
- Technology: handle `UPGRADE_ORBITAL` and `RESEARCH_STIM`; construction owns addons.
- Scout: propose once at or after configured time while `scout_accepted` is false.
- Combat: map `CombatMode.RALLY/DEFEND/ATTACK` to `RALLY_ARMY/DEFEND_BASE/ATTACK_ENEMY`;
  in attack mode use `reinforcement=True` after `board.attack_started`.

Use the exact cost table in the task interface. SCV and Orbital use `TOWNHALL`; Marine uses
`BARRACKS`; addons use `ADDONLESS_BARRACKS`; Marauder uses `TECHLAB_BARRACKS`; Stim uses
`TECHLAB`. Persistent build/upgrade candidates reuse the `ProductionGoal.key`. Scout uses
`scout:enemy_start`. Recurring economy, unit-production, and combat candidates are constructed
directly with
`f"{intent_type.value.lower()}:{board.snapshot.game_loop}"`, so a completed recurring command does
not block a future decision.

- [ ] **Step 4: Run manager tests**

Run:

```bash
pytest tests/hierarchical/test_managers.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sc2_ontology_agent/policy/hierarchical/managers \
  tests/hierarchical/test_managers.py
git commit -m "feat: add hierarchical economy and combat managers"
```

---

### Task 5: Central Command Scheduler

**Files:**

- Create: `src/sc2_ontology_agent/policy/hierarchical/scheduler.py`
- Create: `tests/hierarchical/test_scheduler.py`

**Interfaces:**

- Consumes: `CommandScheduler.select(snapshot, candidates, blackboard)`.
- Produces: conflict-free, stable priority-sorted `list[MacroIntent]`.
- Side effect: calls `blackboard.mark_scheduled(task_key)` and emits schedule/suppression events.

- [ ] **Step 1: Write failing scheduler arbitration tests**

Create `tests/hierarchical/test_scheduler.py`:

```python
from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.policy.hierarchical.commands import CandidateIntent, ProducerKind
from sc2_ontology_agent.policy.hierarchical.scheduler import CommandScheduler

from .conftest import make_snapshot


def make_candidate(
    intent_type: IntentType,
    priority: int,
    task_key: str,
    *,
    minerals: int = 0,
    vespene: int = 0,
    supply: float = 0,
    worker: bool = False,
    producer: ProducerKind | None = None,
    emergency: bool = False,
) -> CandidateIntent:
    return CandidateIntent(
        intent=MacroIntent(
            intent_type,
            priority,
            task_key,
            100,
            {"task_key": task_key, "source_manager": "test"},
        ),
        task_key=task_key,
        mineral_cost=minerals,
        vespene_cost=vespene,
        supply_cost=supply,
        uses_build_worker=worker,
        producer=producer,
        emergency=emergency,
    )


def test_scheduler_reserves_minerals_gas_supply_and_one_worker(blackboard) -> None:
    state = make_snapshot(
        minerals=150,
        vespene=25,
        supply_used=22,
        supply_cap=23,
        idle_barracks_count=1,
        idle_barracks_techlab_count=1,
    )
    candidates = [
        make_candidate(IntentType.BUILD_SUPPLY, 90, "depot", minerals=100, worker=True),
        make_candidate(IntentType.BUILD_REFINERY, 80, "refinery", minerals=75, worker=True),
        make_candidate(
            IntentType.TRAIN_MARAUDER,
            70,
            "marauder",
            minerals=100,
            vespene=25,
            supply=2,
            producer=ProducerKind.TECHLAB_BARRACKS,
        ),
        make_candidate(
            IntentType.TRAIN_MARINE,
            60,
            "marine",
            minerals=50,
            supply=1,
            producer=ProducerKind.BARRACKS,
        ),
    ]

    selected = CommandScheduler().select(state, candidates, blackboard)

    assert [intent.intent_type for intent in selected] == [
        IntentType.BUILD_SUPPLY,
        IntentType.TRAIN_MARINE,
    ]


def test_emergency_defense_preempts_expansion(blackboard) -> None:
    state = make_snapshot(minerals=400, enemy_units_near_base=3)
    candidates = [
        make_candidate(
            IntentType.EXPAND_COMMAND_CENTER,
            40,
            "expand",
            minerals=400,
            worker=True,
        ),
        make_candidate(
            IntentType.DEFEND_BASE,
            100,
            "defend",
            emergency=True,
        ),
    ]

    selected = CommandScheduler().select(state, candidates, blackboard)

    assert [intent.intent_type for intent in selected] == [IntentType.DEFEND_BASE]


def test_scheduler_limits_shared_producer_capacity(blackboard) -> None:
    state = make_snapshot(
        minerals=200,
        supply_cap=50,
        idle_barracks_count=1,
        idle_barracks_techlab_count=1,
    )
    candidates = [
        make_candidate(
            IntentType.TRAIN_MARAUDER,
            70,
            "marauder",
            producer=ProducerKind.TECHLAB_BARRACKS,
        ),
        make_candidate(
            IntentType.TRAIN_MARINE,
            60,
            "marine",
            producer=ProducerKind.BARRACKS,
        ),
    ]

    assert len(CommandScheduler().select(state, candidates, blackboard)) == 1
```

- [ ] **Step 2: Run scheduler tests and verify RED**

Run:

```bash
pytest tests/hierarchical/test_scheduler.py -v
```

Expected: import failure for missing scheduler.

- [ ] **Step 3: Implement stable arbitration**

Implement:

```python
class CommandScheduler:
    def select(
        self,
        snapshot: GameSnapshot,
        candidates: list[CandidateIntent],
        blackboard: StrategicBlackboard,
    ) -> list[MacroIntent]:
        available_minerals = snapshot.minerals
        available_vespene = snapshot.vespene
        available_supply = snapshot.supply_left
        producer_capacity = {
            ProducerKind.TOWNHALL: snapshot.idle_townhall_count,
            ProducerKind.BARRACKS: snapshot.idle_barracks_count,
            ProducerKind.ADDONLESS_BARRACKS: snapshot.addonless_idle_barracks_count,
            ProducerKind.TECHLAB_BARRACKS: snapshot.idle_barracks_techlab_count,
            ProducerKind.TECHLAB: snapshot.idle_techlab_count,
        }
        selected: list[MacroIntent] = []
        worker_reserved = False
        seen: set[tuple[IntentType, str]] = set()
        ordered = sorted(
            enumerate(candidates),
            key=lambda item: (
                not item[1].emergency,
                -item[1].intent.priority,
                item[0],
            ),
        )
        emergency_present = any(candidate.emergency for candidate in candidates)
```

For each candidate, suppress non-emergency expansion/tech when an emergency is present; then
check task schedulability when the task exists, duplicate tuple, pending action, each resource,
the one-worker lock, and producer capacity. Every Barracks-derived producer also consumes one
unit from the total `BARRACKS` capacity; `TECHLAB_BARRACKS` additionally consumes its specialized
capacity, while `ADDONLESS_BARRACKS` additionally consumes its own specialized capacity. Emit
`command_suppressed` with an exact reason for every rejection. On selection, reserve
resources/capacity, mark existing tasks scheduled, and emit `command_scheduled`. Return an
`IDLE` intent only if nothing was selected.

- [ ] **Step 4: Run scheduler and manager tests**

Run:

```bash
pytest tests/hierarchical/test_scheduler.py tests/hierarchical/test_managers.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sc2_ontology_agent/policy/hierarchical/scheduler.py \
  tests/hierarchical/test_scheduler.py
git commit -m "feat: arbitrate hierarchical macro intents"
```

---

### Task 6: Hierarchical Advisor Orchestration

**Files:**

- Create: `src/sc2_ontology_agent/policy/hierarchical/advisor.py`
- Modify: `src/sc2_ontology_agent/policy/hierarchical/__init__.py`
- Modify: `src/sc2_ontology_agent/policy/protocol.py`
- Create: `tests/hierarchical/test_advisor.py`

**Interfaces:**

- Produces: `HierarchicalRulePolicy.recommend(snapshot) -> list[MacroIntent]`.
- Produces: `HierarchicalRulePolicy.observe_execution(intent, result) -> None`.
- Produces: `HierarchicalRulePolicy.drain_events() -> tuple[StrategyEvent, ...]`.
- Produces runtime-checkable `ExecutionAwareAdvisor` and `TraceableAdvisor` protocols.

- [ ] **Step 1: Write failing end-to-end advisor tests**

Create `tests/hierarchical/test_advisor.py`:

```python
from sc2_ontology_agent.config import BotConfig
from sc2_ontology_agent.domain.intent import IntentType
from sc2_ontology_agent.domain.records import ExecutionResult, ExecutionStatus
from sc2_ontology_agent.policy.hierarchical.advisor import HierarchicalRulePolicy

from .conftest import make_snapshot


def test_advisor_progresses_from_opening_to_stim_timing_attack() -> None:
    advisor = HierarchicalRulePolicy(BotConfig())
    opening = advisor.recommend(make_snapshot(
        minerals=500,
        supply_used=14,
        supply_cap=15,
    ))
    assert IntentType.BUILD_SUPPLY in {intent.intent_type for intent in opening}

    tech = advisor.recommend(make_snapshot(
        game_loop=500,
        game_time_seconds=180,
        minerals=500,
        vespene=200,
        supply_cap=60,
        worker_count=30,
        townhall_count=2,
        ready_townhall_count=2,
        orbital_count=1,
        refinery_count=1,
        ready_refinery_count=1,
        supply_depot_count=3,
        ready_supply_depot_count=3,
        barracks_count=2,
        ready_barracks_count=2,
        barracks_techlab_count=1,
        barracks_reactor_count=1,
        idle_barracks_techlab_count=1,
    ))
    assert IntentType.RESEARCH_STIM in {intent.intent_type for intent in tech}

    attack = advisor.recommend(make_snapshot(
        game_loop=1000,
        game_time_seconds=300,
        minerals=500,
        vespene=200,
        supply_cap=100,
        worker_count=44,
        townhall_count=2,
        barracks_count=2,
        barracks_techlab_count=1,
        barracks_reactor_count=1,
        stim_researched=True,
        army_supply=24,
        marine_count=16,
        marauder_count=4,
    ))
    assert IntentType.ATTACK_ENEMY in {intent.intent_type for intent in attack}


def test_execution_feedback_updates_task_and_events() -> None:
    advisor = HierarchicalRulePolicy(BotConfig())
    intents = advisor.recommend(make_snapshot(minerals=500))
    depot = next(
        intent for intent in intents if intent.intent_type is IntentType.BUILD_SUPPLY
    )

    advisor.observe_execution(
        depot,
        ExecutionResult(ExecutionStatus.ACCEPTED),
    )

    assert advisor.blackboard.tasks["build:first_depot"].state.value == "accepted"
    assert "task_state_changed" in {
        event.event_type for event in advisor.drain_events()
    }
```

- [ ] **Step 2: Run advisor tests and verify RED**

Run:

```bash
pytest tests/hierarchical/test_advisor.py -v
```

Expected: import failure for missing advisor.

- [ ] **Step 3: Add optional protocols**

In `policy/protocol.py`:

```python
from typing import Protocol, runtime_checkable

from sc2_ontology_agent.domain.records import ExecutionResult, StrategyEvent


@runtime_checkable
class ExecutionAwareAdvisor(Protocol):
    def observe_execution(
        self,
        intent: MacroIntent,
        result: ExecutionResult,
    ) -> None: ...


@runtime_checkable
class TraceableAdvisor(Protocol):
    def drain_events(self) -> tuple[StrategyEvent, ...]: ...
```

- [ ] **Step 4: Implement advisor call order**

Construct one instance of each controller, manager, scheduler, and blackboard. Implement:

```python
def recommend(self, snapshot: GameSnapshot) -> list[MacroIntent]:
    self.blackboard.update(snapshot)
    self._production_strategy.update(self.blackboard)
    self._combat_strategy.update(self.blackboard)
    candidates: list[CandidateIntent] = []
    for manager in self._managers:
        proposed = manager.propose(self.blackboard)
        candidates.extend(proposed)
        for item in proposed:
            self.blackboard.emit(
                "command_proposed",
                task_key=item.task_key,
                source_manager=str(item.intent.parameters["source_manager"]),
                intent_type=item.intent.intent_type.value,
            )
    return self._scheduler.select(snapshot, candidates, self.blackboard)

def observe_execution(
    self,
    intent: MacroIntent,
    result: ExecutionResult,
) -> None:
    self.blackboard.observe_execution(intent, result)
    if (
        intent.intent_type is IntentType.ATTACK_ENEMY
        and result.status is ExecutionStatus.ACCEPTED
    ):
        self.blackboard.attack_started = True

def drain_events(self) -> tuple[StrategyEvent, ...]:
    return self.blackboard.drain_events()
```

- [ ] **Step 5: Run all pure-policy tests**

Run:

```bash
pytest tests/hierarchical -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/sc2_ontology_agent/policy/protocol.py \
  src/sc2_ontology_agent/policy/hierarchical/advisor.py \
  src/sc2_ontology_agent/policy/hierarchical/__init__.py \
  tests/hierarchical/test_advisor.py
git commit -m "feat: orchestrate hierarchical rule policy"
```

---

### Task 7: Economy and Construction Execution

**Files:**

- Modify: `src/sc2_ontology_agent/execution/simple_executor.py:20-91`
- Create: `tests/executor_fakes.py`
- Modify: `tests/test_simple_executor.py`

**Interfaces:**

- Consumes: `BUILD_REFINERY`, `EXPAND_COMMAND_CENTER`, `BUILD_TECHLAB`, `BUILD_REACTOR`.
- Extends: `DISTRIBUTE_WORKERS` with optional `resource_priority`.
- Preserves existing execution status meanings.

- [ ] **Step 1: Write failing executor tests with focused fakes**

Create `tests/executor_fakes.py` with the reusable behavior required by Tasks 7–9:

```python
from __future__ import annotations

from types import SimpleNamespace
from typing import Callable, Iterable

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

    def __iter__(self):
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
        return FakeGroup(
            unit for unit in self.members if unit.distance_to(target) < distance
        )

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
            unit
            for unit_type in unit_types
            for unit in self.values.get(unit_type, FakeGroup())
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
```

Import the support in `tests/test_simple_executor.py` with:

```python
from executor_fakes import ExecutorFakeBot, FakeGroup, FakeTypedCollection, FakeUnit
from sc2.ids.ability_id import AbilityId
from sc2.ids.upgrade_id import UpgradeId
from sc2.position import Point2
```

Each test constructs `ExecutorFakeBot`, then assigns only the groups needed for the scenario.
For example, a free-geyser setup is:

```python
bot = ExecutorFakeBot()
townhall = FakeUnit(10, Point2((0, 0)))
bot.townhalls = FakeGroup([townhall])
bot.geyser = FakeUnit(20, Point2((5, 0)))
bot.vespene_geyser = FakeGroup([bot.geyser])
```

Add tests that assert:

```python
def test_build_refinery_selects_free_geyser_and_worker() -> None:
    bot = ExecutorFakeBot()
    bot.townhalls = FakeGroup([FakeUnit(10, Point2((0, 0)))])
    bot.geyser = FakeUnit(20, Point2((5, 0)))
    bot.vespene_geyser = FakeGroup([bot.geyser])
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(MacroIntent(
        IntentType.BUILD_REFINERY,
        70,
        "first_refinery",
        100,
    )))

    assert result.status is ExecutionStatus.ACCEPTED
    assert bot.worker.builds == [(UnitTypeId.REFINERY, bot.geyser)]


def test_expand_fails_when_no_expansion_location_exists() -> None:
    bot = ExecutorFakeBot()
    bot.townhalls = FakeGroup([FakeUnit(10, Point2((0, 0)))])
    bot.next_expansion = None
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(MacroIntent(
        IntentType.EXPAND_COMMAND_CENTER,
        40,
        "expansion",
        100,
    )))

    assert result == ExecutionResult(
        ExecutionStatus.FAILED,
        "expansion_location_not_found",
    )


@pytest.mark.parametrize(
    "intent_type,unit_type",
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
    bot.structures = FakeTypedCollection({
        UnitTypeId.BARRACKS: FakeGroup([bot.barracks]),
    })
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(
        MacroIntent(intent_type, 50, "addon", 100)
    ))

    assert result.status is ExecutionStatus.ACCEPTED
    assert bot.barracks.builds == [(unit_type, None)]
```

Implement the fake collections only with properties the executor reads; do not instantiate
real SC2 clients.

- [ ] **Step 2: Run focused executor tests and verify RED**

Run:

```bash
pytest tests/test_simple_executor.py -k \
  "refinery or expansion or addon or distribution" -v
```

Expected: handler lookup failures for the new intent types.

- [ ] **Step 3: Implement economy and construction handlers**

Add handlers and implement:

```python
async def _build_refinery(self) -> ExecutionResult:
    if not self._bot.townhalls.ready:
        return ExecutionResult(ExecutionStatus.REJECTED, "no_ready_townhall")
    geysers = self._bot.vespene_geyser.closer_than(
        15,
        self._bot.townhalls.ready.first,
    )
    available = geysers.filter(
        lambda geyser: not self._bot.gas_buildings.closer_than(1.0, geyser)
    )
    if not available:
        return ExecutionResult(ExecutionStatus.REJECTED, "no_free_geyser")
    return await self._build_at(UnitTypeId.REFINERY, available.closest_to(
        self._bot.townhalls.ready.first
    ))
```

Use `await self._bot.get_next_expansion()` for expansion, `select_build_worker()` for both
refinery and Command Center, and explicit failure reasons. Select a ready idle Barracks with
`add_on_tag == 0` for addon intents and issue
`barracks.build(UnitTypeId.BARRACKSTECHLAB)` or
`barracks.build(UnitTypeId.BARRACKSREACTOR)`. Pass `resource_ratio=1.5` for gas priority and
`resource_ratio=2.0` for mineral priority to `distribute_workers()`.

- [ ] **Step 4: Run the complete executor suite**

Run:

```bash
pytest tests/test_simple_executor.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sc2_ontology_agent/execution/simple_executor.py tests/test_simple_executor.py
git commit -m "feat: execute hierarchical economy and construction intents"
```

---

### Task 8: Production and Technology Execution

**Files:**

- Modify: `src/sc2_ontology_agent/execution/simple_executor.py`
- Modify: `tests/test_simple_executor.py`

**Interfaces:**

- Consumes: `UPGRADE_ORBITAL`, `RESEARCH_STIM`, `TRAIN_MARAUDER`.
- Uses: `AbilityId.UPGRADETOORBITAL_ORBITALCOMMAND` and `UpgradeId.STIMPACK`.

- [ ] **Step 1: Write failing production and technology tests**

Add:

```python
def test_orbital_upgrade_uses_idle_command_center() -> None:
    bot = ExecutorFakeBot()
    bot.command_center = FakeUnit(10, Point2((0, 0)))
    bot.structures = FakeTypedCollection({
        UnitTypeId.COMMANDCENTER: FakeGroup([bot.command_center]),
    })
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(MacroIntent(
        IntentType.UPGRADE_ORBITAL,
        70,
        "orbital",
        100,
    )))

    assert result.status is ExecutionStatus.ACCEPTED
    assert bot.command_center.abilities == [
        AbilityId.UPGRADETOORBITAL_ORBITALCOMMAND
    ]


def test_stim_research_uses_idle_techlab() -> None:
    bot = ExecutorFakeBot()
    bot.techlab = FakeUnit(40, Point2((6, 0)))
    bot.structures = FakeTypedCollection({
        UnitTypeId.BARRACKSTECHLAB: FakeGroup([bot.techlab]),
    })
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(MacroIntent(
        IntentType.RESEARCH_STIM,
        70,
        "stim",
        100,
    )))

    assert result.status is ExecutionStatus.ACCEPTED
    assert bot.techlab.researched == [UpgradeId.STIMPACK]


def test_marauder_requires_idle_barracks_with_techlab() -> None:
    bot = ExecutorFakeBot()
    bot.structures = FakeTypedCollection({
        UnitTypeId.BARRACKS: FakeGroup([FakeUnit(30, Point2((4, 0)))]),
        UnitTypeId.BARRACKSTECHLAB: FakeGroup(),
    })
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(MacroIntent(
        IntentType.TRAIN_MARAUDER,
        60,
        "bio_ratio",
        100,
    )))

    assert result == ExecutionResult(
        ExecutionStatus.REJECTED,
        "techlab_barracks_missing",
    )
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
pytest tests/test_simple_executor.py -k "orbital or stim or marauder" -v
```

Expected: missing handler failures.

- [ ] **Step 3: Implement production and technology handlers**

Import `AbilityId` and `UpgradeId`. Guard resources, supply, ready/idle state, and existing
upgrade. Locate a Marauder producer by matching a ready idle Barracks `add_on_tag` to a ready
Tech Lab tag. Return `waiting` for busy valid facilities, `rejected` for absent prerequisites,
and `failed` only when the command returns `False`.

- [ ] **Step 4: Run executor tests**

Run:

```bash
pytest tests/test_simple_executor.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sc2_ontology_agent/execution/simple_executor.py tests/test_simple_executor.py
git commit -m "feat: execute bio production and technology intents"
```

---

### Task 9: Scout, Rally, Defense, and Attack Execution

**Files:**

- Modify: `src/sc2_ontology_agent/execution/simple_executor.py`
- Modify: `tests/test_simple_executor.py`

**Interfaces:**

- Consumes: `SCOUT_ENEMY_START`, `RALLY_ARMY`, `DEFEND_BASE`, `ATTACK_ENEMY`.
- `ATTACK_ENEMY_START` remains unchanged for `SimpleRulePolicy`.

- [ ] **Step 1: Write failing combat execution tests**

Add:

```python
def test_scout_moves_one_worker_to_enemy_start() -> None:
    bot = ExecutorFakeBot()
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(MacroIntent(
        IntentType.SCOUT_ENEMY_START,
        30,
        "scout_window",
        100,
    )))

    assert result.status is ExecutionStatus.ACCEPTED
    assert bot.worker.moves == [bot.enemy_start]


def test_rally_moves_only_idle_bio_units_to_staging_point() -> None:
    bot = ExecutorFakeBot()
    home = FakeUnit(10, Point2((0, 0)))
    bot.townhalls = FakeGroup([home])
    bot.idle_marine = FakeUnit(50, Point2((1, 0)))
    bot.busy_marauder = FakeUnit(51, Point2((1, 1)), idle=False)
    bot.units = FakeTypedCollection({
        UnitTypeId.MARINE: FakeGroup([bot.idle_marine]),
        UnitTypeId.MARAUDER: FakeGroup([bot.busy_marauder]),
    })
    bot.expected_rally = Point2((35, 0))
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig(rally_map_fraction=0.35))

    result = asyncio.run(executor.execute(MacroIntent(
        IntentType.RALLY_ARMY,
        50,
        "muster",
        100,
    )))

    assert result.status is ExecutionStatus.ACCEPTED
    assert bot.idle_marine.moves == [bot.expected_rally]
    assert bot.busy_marauder.moves == []


def test_defense_targets_enemy_closest_to_ready_townhall() -> None:
    bot = ExecutorFakeBot()
    home = FakeUnit(10, Point2((0, 0)))
    bot.townhalls = FakeGroup([home])
    bot.marine = FakeUnit(50, Point2((1, 0)))
    bot.units = FakeTypedCollection({
        UnitTypeId.MARINE: FakeGroup([bot.marine]),
    })
    bot.closest_threat = FakeUnit(70, Point2((5, 0)))
    far_threat = FakeUnit(71, Point2((20, 0)))
    bot.enemy_units = FakeGroup([far_threat, bot.closest_threat])
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(MacroIntent(
        IntentType.DEFEND_BASE,
        100,
        "base_threat",
        100,
    )))

    assert result.status is ExecutionStatus.ACCEPTED
    assert bot.marine.targets == [bot.closest_threat]


def test_hierarchical_attack_uses_idle_reinforcements_after_first_wave() -> None:
    bot = ExecutorFakeBot()
    bot.idle_marine = FakeUnit(50, Point2((1, 0)))
    bot.busy_marauder = FakeUnit(51, Point2((1, 1)), idle=False)
    bot.units = FakeTypedCollection({
        UnitTypeId.MARINE: FakeGroup([bot.idle_marine]),
        UnitTypeId.MARAUDER: FakeGroup([bot.busy_marauder]),
    })
    executor = SimpleExecutor(cast(BotAI, bot), BotConfig())

    result = asyncio.run(executor.execute(MacroIntent(
        IntentType.ATTACK_ENEMY,
        60,
        "reinforcement",
        100,
        {"reinforcement": True},
    )))

    assert result.status is ExecutionStatus.ACCEPTED
    assert bot.idle_marine.targets == [bot.enemy_start]
    assert bot.busy_marauder.targets == []
```

- [ ] **Step 2: Run tactical tests and verify RED**

Run:

```bash
pytest tests/test_simple_executor.py -k \
  "scout or rally or defense or hierarchical_attack" -v
```

Expected: missing handler failures.

- [ ] **Step 3: Implement tactical handlers**

Create one `_bio_units()` helper that combines Marine and Marauder collections only inside the
executor. Rally point:

```python
rally = home.position.towards(
    enemy_start,
    home.distance_to(enemy_start) * self._config.rally_map_fraction,
)
```

Scout chooses a worker that is idle if possible and is not carrying resources. Defense filters
visible enemies within `defense_radius` of ready townhalls and attacks the closest threat.
Hierarchical attack shares the existing visible-structure/enemy-start fallback but includes both
bio unit types. Preserve all-vs-idle reinforcement semantics.

- [ ] **Step 4: Run executor regression suite**

Run:

```bash
pytest tests/test_simple_executor.py -v
```

Expected: PASS, including old Marine-only attack tests.

- [ ] **Step 5: Commit**

```bash
git add src/sc2_ontology_agent/execution/simple_executor.py tests/test_simple_executor.py
git commit -m "feat: execute hierarchical scout and combat intents"
```

---

### Task 10: Bot Snapshot, Advisor Feedback, Strategy Events, and Metrics

**Files:**

- Modify: `src/sc2_ontology_agent/bot.py:74-136,193-229`
- Modify: `src/sc2_ontology_agent/logging/metrics.py`
- Modify: `tests/test_bot_snapshot.py`
- Modify: `tests/test_metrics.py`
- Create: `tests/test_bot_advisor_feedback.py`

**Interfaces:**

- Bot recognizes runtime-checkable `ExecutionAwareAdvisor` and `TraceableAdvisor`.
- Metrics consumes `StrategyEvent` through `record_strategy_event(event)`.
- Snapshot adapter computes all facts declared in Task 1.

- [ ] **Step 1: Write failing snapshot, feedback, and metrics tests**

Extend `FakeSnapshotBot` with fake townhalls, Orbitals, Refineries, addons, Marauders, upgrades,
and base-near enemy filtering. Assert:

```python
assert snapshot.townhall_count == 2
assert snapshot.orbital_count == 1
assert snapshot.refinery_count == 1
assert snapshot.barracks_techlab_count == 1
assert snapshot.barracks_reactor_count == 1
assert snapshot.marauder_count == 3
assert snapshot.army_supply == 13.0
assert snapshot.enemy_units_near_base == 2
assert snapshot.stim_researched is True
assert all(
    isinstance(value, int | float | bool | tuple)
    for value in snapshot.to_dict().values()
)
```

Create `tests/test_bot_advisor_feedback.py` with a fake advisor implementing all three methods:

```python
import asyncio
from pathlib import Path
from typing import cast

from sc2_ontology_agent.bot import OntologySc2Bot
from sc2_ontology_agent.config import BotConfig, GameConfig, LoggingConfig
from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.domain.records import (
    ExecutionResult,
    ExecutionStatus,
    StrategyEvent,
)
from sc2_ontology_agent.domain.state import GameSnapshot
from sc2_ontology_agent.logging.event_logger import EventLogger
from sc2_ontology_agent.logging.metrics import MetricsCollector


class FakeTraceableAdvisor:
    def __init__(self) -> None:
        self.feedback: list[tuple[MacroIntent, ExecutionResult]] = []
        self.events: list[StrategyEvent] = []

    def recommend(self, _snapshot: GameSnapshot) -> list[MacroIntent]:
        return []

    def observe_execution(
        self,
        intent: MacroIntent,
        result: ExecutionResult,
    ) -> None:
        self.feedback.append((intent, result))
        self.events.append(StrategyEvent(
            "task_state_changed",
            intent.created_at_game_loop,
            5.0,
            {"state": result.status.value},
        ))

    def drain_events(self) -> tuple[StrategyEvent, ...]:
        drained = tuple(self.events)
        self.events.clear()
        return drained


class RecordingEventLogger:
    def __init__(self) -> None:
        self.event_types: list[str] = []

    def log(self, event_type: str, **_values: object) -> None:
        self.event_types.append(event_type)


class AcceptedExecutor:
    async def execute(self, _intent: MacroIntent) -> ExecutionResult:
        return ExecutionResult(ExecutionStatus.ACCEPTED)


def make_bot(
    tmp_path: Path,
    *,
    advisor: FakeTraceableAdvisor,
    logger: RecordingEventLogger,
    metrics: MetricsCollector,
) -> OntologySc2Bot:
    return OntologySc2Bot(
        bot_config=BotConfig(),
        game_config=GameConfig(),
        logging_config=LoggingConfig(),
        advisor=advisor,
        event_logger=cast(EventLogger, logger),
        metrics=metrics,
        metrics_path=tmp_path / "metrics.json",
        replay_path=None,
    )


def test_bot_returns_execution_feedback_and_drains_strategy_events(tmp_path: Path) -> None:
    advisor = FakeTraceableAdvisor()
    logger = RecordingEventLogger()
    metrics = MetricsCollector("run-1")
    bot = make_bot(tmp_path, advisor=advisor, logger=logger, metrics=metrics)
    snapshot = GameSnapshot.empty(game_loop=100, game_time_seconds=5.0)
    intent = MacroIntent(IntentType.TRAIN_MARINE, 60, "test", 100)
    bot._executor = AcceptedExecutor()

    asyncio.run(bot._execute_and_record(snapshot, intent))

    assert advisor.feedback == [
        (intent, ExecutionResult(ExecutionStatus.ACCEPTED))
    ]
    assert "task_state_changed" in logger.event_types
```

Add to `tests/test_metrics.py`:

```python
def test_strategy_events_add_optional_hierarchical_metrics() -> None:
    collector = MetricsCollector("run-1")
    collector.record_strategy_event(StrategyEvent(
        "strategy_phase_changed",
        100,
        10.0,
        {"phase": "expansion"},
    ))
    collector.record_strategy_event(StrategyEvent(
        "command_suppressed",
        110,
        11.0,
        {"reason": "insufficient_minerals"},
    ))
    collector.record_strategy_event(StrategyEvent(
        "task_state_changed",
        120,
        12.0,
        {"state": "failed"},
    ))

    metrics = collector.finalize("Victory", GameSnapshot.empty(), None, None)

    assert metrics["production_phase_reached"] == "expansion"
    assert metrics["command_suppression_count"] == 1
    assert metrics["task_failure_count"] == 1
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
pytest tests/test_bot_snapshot.py tests/test_bot_advisor_feedback.py tests/test_metrics.py -v
```

Expected: failures for absent snapshot facts, no feedback/drain calls, and no strategy metrics.

- [ ] **Step 3: Expand snapshot creation**

Use `UnitTypeId.COMMANDCENTER`, `ORBITALCOMMAND`, `PLANETARYFORTRESS`, `REFINERY`,
`BARRACKSTECHLAB`, `BARRACKSREACTOR`, and `MARAUDER`; use `UpgradeId.STIMPACK`.
Compute signed harvester deficits from `ideal_harvesters - assigned_harvesters`. Count visible
combat enemies near any ready townhall using `defense_radius`. Extend pending-action mapping for
all new train/build/addon intents and set `stim_pending` with `already_pending_upgrade()`.

- [ ] **Step 4: Deliver feedback and drain events**

After every `recommend()` and `observe_execution()`:

```python
def _drain_strategy_events(self) -> None:
    if not isinstance(self._advisor, TraceableAdvisor):
        return
    for event in self._advisor.drain_events():
        self._event_logger.log(
            event.event_type,
            game_loop=event.game_loop,
            game_time_seconds=event.game_time_seconds,
            details=dict(event.details),
        )
        self._metrics.record_strategy_event(event)
```

Call `observe_execution()` only when `isinstance(advisor, ExecutionAwareAdvisor)`. Treat both
`ATTACK_ENEMY_START` and `ATTACK_ENEMY` accepted results as first attack.

- [ ] **Step 5: Extend metrics**

Map strategy events exactly:

- latest `strategy_phase_changed.details["phase"]` -> `production_phase_reached`;
- accepted `task_state_changed` for `scout:enemy_start` -> `first_scout_time_seconds`;
- accepted `task_state_changed` for `build:expansion` -> `first_expansion_time_seconds`;
- completed `task_state_changed` for `research:stim` -> `stim_completed_time_seconds`;
- first `combat_mode_changed` with mode `defend` -> `first_defense_time_seconds`;
- every `task_state_changed` with state `failed` -> `task_failure_count`;
- every `command_suppressed` -> `command_suppression_count`.

Always include these keys in finalized metrics with `None`/zero defaults so every run has a stable
schema.

- [ ] **Step 6: Run focused and existing bot/logging tests**

Run:

```bash
pytest tests/test_bot_snapshot.py tests/test_bot_advisor_feedback.py \
  tests/test_metrics.py tests/test_event_logger.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/sc2_ontology_agent/bot.py src/sc2_ontology_agent/logging/metrics.py \
  tests/test_bot_snapshot.py tests/test_bot_advisor_feedback.py tests/test_metrics.py
git commit -m "feat: connect hierarchical feedback and telemetry"
```

---

### Task 11: Policy Factory, Runtime Defaults, and Documentation

**Files:**

- Create: `src/sc2_ontology_agent/policy/factory.py`
- Modify: `src/sc2_ontology_agent/runner.py:16-18,72-81`
- Create: `tests/test_policy_factory.py`
- Modify: `tests/test_runner.py`
- Modify: `configs/dev.yaml`
- Modify: `configs/batch.yaml`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/experiment-data.md`
- Modify: `docs/roadmap.md`

**Interfaces:**

- Produces: `create_advisor(config: BotConfig) -> TacticalAdvisor`.
- Runner creates a fresh advisor per game.
- Example configs select `hierarchical` and contain every non-obvious strategy threshold.

- [ ] **Step 1: Write failing factory tests**

Create `tests/test_policy_factory.py`:

```python
from sc2_ontology_agent.config import BotConfig
from sc2_ontology_agent.policy.factory import create_advisor
from sc2_ontology_agent.policy.hierarchical.advisor import HierarchicalRulePolicy
from sc2_ontology_agent.policy.simple_rule_policy import SimpleRulePolicy


def test_factory_defaults_to_fresh_hierarchical_advisors() -> None:
    first = create_advisor(BotConfig())
    second = create_advisor(BotConfig())

    assert isinstance(first, HierarchicalRulePolicy)
    assert isinstance(second, HierarchicalRulePolicy)
    assert first is not second


def test_factory_keeps_simple_policy_selectable() -> None:
    advisor = create_advisor(BotConfig(policy="simple"))

    assert isinstance(advisor, SimpleRulePolicy)
```

Update a runner test to monkeypatch `create_advisor`, run the missing-SC2 path, and assert it was
called once with `config.bot`.

- [ ] **Step 2: Run factory and runner tests and verify RED**

Run:

```bash
pytest tests/test_policy_factory.py tests/test_runner.py -v
```

Expected: import failure for missing factory.

- [ ] **Step 3: Implement and wire the factory**

Create:

```python
def create_advisor(config: BotConfig) -> TacticalAdvisor:
    if config.policy == "simple":
        return SimpleRulePolicy(config)
    if config.policy == "hierarchical":
        return HierarchicalRulePolicy(config)
    raise ValueError(f"unsupported policy: {config.policy}")
```

Replace the direct `SimpleRulePolicy(config.bot)` construction in runner with
`create_advisor(config.bot)`.

- [ ] **Step 4: Update example configurations**

Set both config files to the approved values:

```yaml
bot:
  policy: hierarchical
  worker_limit: 44
  attack_marine_threshold: 10
  supply_buffer: 6
  max_barracks: 2
  decision_interval_steps: 4
  build_search_radius: 20
  building_spacing: 7
  expansion_worker_threshold: 20
  scout_start_time_seconds: 90
  attack_army_supply: 24
  reinforcement_army_supply: 8
  marine_to_marauder_ratio: 2
  defense_radius: 30
  rally_map_fraction: 0.35
  task_retry_limit: 3
  task_retry_cooldown_steps: 2
  task_timeout_seconds: 120
```

- [ ] **Step 5: Update user and architecture documentation**

Document:

- `hierarchical` as the default and `simple` as the ablation option;
- the two strategy tiers, six managers, scheduler, and optional feedback protocols;
- the two-base Marine/Marauder Stim behavior and explicit non-goals;
- every new config key;
- new event types and metrics fields;
- that this is a Terran/BurnySc2 architectural adaptation, not the paper's Zerg result;
- V0.2 hierarchical-agent items as implemented while leaving V0.3 ontology work pending;
- unchanged opt-in integration-test warning.

- [ ] **Step 6: Run config, factory, runner, and documentation-sensitive tests**

Run:

```bash
pytest tests/test_config.py tests/test_policy_factory.py tests/test_runner.py -v
python -m sc2_ontology_agent check-env --config configs/dev.yaml
```

Expected: pytest PASS. `check-env` may return nonzero only for missing local SC2/map; its rendered
configuration section must not report a config parse error.

- [ ] **Step 7: Commit**

```bash
git add src/sc2_ontology_agent/policy/factory.py src/sc2_ontology_agent/runner.py \
  tests/test_policy_factory.py tests/test_runner.py configs/dev.yaml configs/batch.yaml \
  README.md docs/architecture.md docs/experiment-data.md docs/roadmap.md
git commit -m "feat: enable hierarchical rule agent by default"
```

---

### Task 12: Full Regression and Acceptance Verification

**Files:**

- Modify only files implicated by verification failures.

**Interfaces:**

- Verifies every requirement in
  `docs/superpowers/specs/2026-07-30-hierarchical-rule-agent-design.md`.
- Does not run real SC2 unless `RUN_SC2_INTEGRATION=1` was explicitly requested and the environment
  is ready.

- [ ] **Step 1: Run the complete unit suite**

Run:

```bash
pytest
```

Expected: all non-integration tests PASS and the integration test is skipped.

- [ ] **Step 2: Run lint**

Run:

```bash
ruff check .
```

Expected: no violations.

- [ ] **Step 3: Run formatting verification**

Run:

```bash
ruff format --check .
```

Expected: all files already formatted.

- [ ] **Step 4: Run strict type checking**

Run:

```bash
mypy src
```

Expected: success with no issues.

- [ ] **Step 5: Verify both policy configurations parse**

Run:

```bash
python -m sc2_ontology_agent check-env --config configs/dev.yaml
```

Create a temporary config under `/tmp` with `bot.policy: simple`, run the same command against it,
and remove only that exact temporary file afterward. Environment failures for absent SC2/map are
acceptable; configuration failures are not.

- [ ] **Step 6: Review the diff against the spec**

Run:

```bash
git diff --check
git status --short
```

Manually confirm the diff contains no generated `runs/`, `replays/`, SC2 binaries, maps, replay
files, credentials, or machine-specific paths.

- [ ] **Step 7: Close verification**

If any check fails, return to the task that owns the failing behavior, add or retain its
reproducing test, fix it there, rerun that task's focused command, and then repeat Steps 1–6.
After all checks pass, do not create an empty verification commit.
