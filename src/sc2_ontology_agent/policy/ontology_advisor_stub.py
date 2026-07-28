from sc2_ontology_agent.domain.intent import MacroIntent
from sc2_ontology_agent.domain.state import GameSnapshot


class OntologyAdvisorStub:
    """V0.3 replacement seam; intentionally performs no ontology reasoning."""

    def recommend(self, snapshot: GameSnapshot) -> list[MacroIntent]:
        del snapshot
        return []
