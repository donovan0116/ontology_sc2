from pathlib import Path

import pytest

from sc2_ontology_agent.config import ConfigError, load_config


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
