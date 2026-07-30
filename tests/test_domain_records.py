from sc2_ontology_agent.domain.records import StrategyEvent


def test_strategy_event_preserves_framework_independent_scalar_details() -> None:
    details = {
        "phase": "opening",
        "retry_count": 2,
        "confidence": 0.75,
        "enemy_seen": True,
        "target": None,
    }

    event = StrategyEvent(
        event_type="SCOUT_STARTED",
        game_loop=224,
        game_time_seconds=10.0,
        details=details,
    )

    assert event.event_type == "SCOUT_STARTED"
    assert event.game_loop == 224
    assert event.game_time_seconds == 10.0
    assert event.details == details
