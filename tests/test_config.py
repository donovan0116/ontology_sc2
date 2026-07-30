from pathlib import Path

import pytest

from sc2_ontology_agent.config import ConfigError, load_config


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
        ("bot:\n  scout_start_time_seconds: 0\n", "scout_start_time_seconds"),
        ("bot:\n  task_retry_cooldown_steps: 0\n", "task_retry_cooldown_steps"),
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


def test_load_config_applies_defaults_and_explicit_values(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
bot:
  worker_limit: 18
experiment:
  output_root: custom-runs
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.bot.worker_limit == 18
    assert config.game.map_name == "AcropolisLE"
    assert config.experiment.output_root == Path("custom-runs")
    assert config.player.race == "Terran"


@pytest.mark.parametrize(
    "yaml_text, message",
    [
        ("bot:\n  worker_limt: 10\n", "unknown field"),
        ("bot:\n  worker_limit: 0\n", "worker_limit"),
        ("opponent:\n  difficulty: Impossible\n", "difficulty"),
        ("game:\n  realtime: yes\n", "realtime"),
        ("extra: true\n", "unknown section"),
        ("experiment:\n  run_name: ../escape\n", "run_name"),
        ("experiment:\n  run_name: a/b\n", "run_name"),
    ],
)
def test_invalid_config_is_rejected(tmp_path: Path, yaml_text: str, message: str) -> None:
    config_path = tmp_path / "invalid.yaml"
    config_path.write_text(yaml_text, encoding="utf-8")

    with pytest.raises(ConfigError, match=message):
        load_config(config_path)
