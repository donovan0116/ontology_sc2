from typing import Protocol

from sc2_ontology_agent.domain.intent import MacroIntent
from sc2_ontology_agent.domain.state import GameSnapshot


class TacticalAdvisor(Protocol):
    """Replaceable high-level recommendation boundary."""

    def recommend(self, snapshot: GameSnapshot) -> list[MacroIntent]: ...
