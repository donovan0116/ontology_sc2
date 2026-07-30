"""Hierarchical macro-policy orchestration."""

from sc2_ontology_agent.config import BotConfig
from sc2_ontology_agent.domain.intent import IntentType, MacroIntent
from sc2_ontology_agent.domain.records import ExecutionResult, ExecutionStatus, StrategyEvent
from sc2_ontology_agent.domain.state import GameSnapshot
from sc2_ontology_agent.policy.hierarchical.blackboard import StrategicBlackboard
from sc2_ontology_agent.policy.hierarchical.combat_strategy import CombatStrategy
from sc2_ontology_agent.policy.hierarchical.commands import CandidateIntent
from sc2_ontology_agent.policy.hierarchical.managers.combat import CombatManager
from sc2_ontology_agent.policy.hierarchical.managers.construction import ConstructionManager
from sc2_ontology_agent.policy.hierarchical.managers.economy import EconomyManager
from sc2_ontology_agent.policy.hierarchical.managers.production import ProductionManager
from sc2_ontology_agent.policy.hierarchical.managers.scout import ScoutManager
from sc2_ontology_agent.policy.hierarchical.managers.technology import TechnologyManager
from sc2_ontology_agent.policy.hierarchical.production_strategy import ProductionStrategy
from sc2_ontology_agent.policy.hierarchical.scheduler import CommandScheduler


class HierarchicalRulePolicy:
    """Coordinate strategic controllers, managers, and macro arbitration."""

    def __init__(self, config: BotConfig) -> None:
        self.blackboard = StrategicBlackboard(config)
        self._production_strategy = ProductionStrategy()
        self._combat_strategy = CombatStrategy()
        self._managers = (
            EconomyManager(),
            ConstructionManager(),
            TechnologyManager(),
            ProductionManager(),
            ScoutManager(),
            CombatManager(),
        )
        self._scheduler = CommandScheduler()

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
        return tuple(self.blackboard.drain_events())
