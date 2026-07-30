"""Policy selection for runtime game advisors."""

from sc2_ontology_agent.config import BotConfig
from sc2_ontology_agent.policy.hierarchical.advisor import HierarchicalRulePolicy
from sc2_ontology_agent.policy.protocol import TacticalAdvisor
from sc2_ontology_agent.policy.simple_rule_policy import SimpleRulePolicy


def create_advisor(config: BotConfig) -> TacticalAdvisor:
    """Create an independent tactical advisor for one game."""

    if config.policy == "simple":
        return SimpleRulePolicy(config)
    if config.policy == "hierarchical":
        return HierarchicalRulePolicy(config)
    raise ValueError(f"unsupported policy: {config.policy}")
