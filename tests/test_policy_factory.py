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
