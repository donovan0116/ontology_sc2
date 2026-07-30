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
