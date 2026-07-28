"""Tactical recommendation interfaces and V0.1 implementations."""

from sc2_ontology_agent.policy.protocol import TacticalAdvisor
from sc2_ontology_agent.policy.simple_rule_policy import SimpleRulePolicy

__all__ = ["SimpleRulePolicy", "TacticalAdvisor"]
