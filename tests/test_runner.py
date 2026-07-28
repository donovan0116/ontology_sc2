import json
from asyncio import run as run_async
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest
from sc2.data import Result

from sc2_ontology_agent.config import AppConfig, ExperimentConfig
from sc2_ontology_agent.domain.state import GameSnapshot
from sc2_ontology_agent.runner import GameRunError, run_batch, run_single_game


def test_missing_sc2_writes_clear_single_run_failure_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AppConfig(
        experiment=ExperimentConfig(
            output_root=tmp_path / "runs",
            replay_root=tmp_path / "replays",
        )
    )
    monkeypatch.setattr(
        "sc2_ontology_agent.runner.discover_sc2_install",
        lambda: (None, None),
        raising=False,
    )

    with pytest.raises(GameRunError, match="StarCraft II installation not found") as captured:
        run_single_game(config, "missing-sc2")

    run_directory = config.experiment.output_root / "missing-sc2"
    assert captured.value.run_id == "missing-sc2"
    assert (run_directory / "config.yaml").is_file()
    assert (run_directory / "events.jsonl").is_file()
    assert (run_directory / "metrics.json").is_file()
    error = json.loads((run_directory / "error.json").read_text(encoding="utf-8"))
    assert error["exception_type"] == "RuntimeError"


def test_burnysc2_swallowed_start_error_is_persisted_as_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AppConfig(
        experiment=ExperimentConfig(
            output_root=tmp_path / "runs",
            replay_root=tmp_path / "replays",
        )
    )
    maps_directory = tmp_path / "Maps"
    maps_directory.mkdir()
    monkeypatch.setattr(
        "sc2_ontology_agent.runner.discover_sc2_install",
        lambda: (tmp_path, maps_directory),
    )
    monkeypatch.setattr("sc2_ontology_agent.runner.map_exists", lambda *_args: True)
    monkeypatch.setattr("sc2_ontology_agent.runner.maps.get", lambda _name: object())

    def swallowed_start_error(_map: object, players: list[Any], **_kwargs: object) -> Result:
        bot = players[0].ai

        def crash_snapshot() -> object:
            raise RuntimeError("snapshot adapter crashed")

        bot.client = type("Client", (), {"game_step": 0})()
        bot.create_snapshot = crash_snapshot
        with suppress(RuntimeError):
            run_async(bot.on_start())
        run_async(bot.on_end(Result.Defeat))
        return Result.Defeat

    monkeypatch.setattr("sc2_ontology_agent.runner.run_game", swallowed_start_error)

    with pytest.raises(GameRunError, match="snapshot adapter crashed") as captured:
        run_single_game(config, "swallowed-start")

    assert captured.value.metrics["result"] == "Error"
    error_path = config.experiment.output_root / "swallowed-start" / "error.json"
    error = json.loads(error_path.read_text(encoding="utf-8"))
    assert error["exception_type"] == "RuntimeError"


def test_exception_after_on_end_upgrades_metrics_to_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AppConfig(
        experiment=ExperimentConfig(
            output_root=tmp_path / "runs",
            replay_root=tmp_path / "replays",
        )
    )
    maps_directory = tmp_path / "Maps"
    maps_directory.mkdir()
    monkeypatch.setattr(
        "sc2_ontology_agent.runner.discover_sc2_install",
        lambda: (tmp_path, maps_directory),
    )
    monkeypatch.setattr("sc2_ontology_agent.runner.map_exists", lambda *_args: True)
    monkeypatch.setattr("sc2_ontology_agent.runner.maps.get", lambda _name: object())

    def replay_failure(_map: object, players: list[Any], **_kwargs: object) -> Result:
        bot = players[0].ai
        bot.create_snapshot = lambda: GameSnapshot.empty(game_loop=100, game_time_seconds=5.0)
        run_async(bot.on_end(Result.Victory))
        raise RuntimeError("replay save failed")

    monkeypatch.setattr("sc2_ontology_agent.runner.run_game", replay_failure)

    with pytest.raises(GameRunError, match="replay save failed") as captured:
        run_single_game(config, "replay-failure")

    assert captured.value.metrics["result"] == "Error"
    assert "replay save failed" in str(captured.value.metrics["exception"])
    metrics_path = config.experiment.output_root / "replay-failure" / "metrics.json"
    persisted = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert persisted["result"] == "Error"


def test_external_run_id_cannot_escape_output_root(tmp_path: Path) -> None:
    config = AppConfig(
        experiment=ExperimentConfig(
            output_root=tmp_path / "runs",
            replay_root=tmp_path / "replays",
        )
    )

    with pytest.raises(ValueError, match="run_id"):
        run_single_game(config, "../escape")

    assert not (tmp_path / "escape").exists()


def test_single_failure_does_not_destroy_batch_summary(tmp_path: Path) -> None:
    config = AppConfig(
        experiment=ExperimentConfig(
            run_name="test",
            games=3,
            output_root=tmp_path / "runs",
            replay_root=tmp_path / "replays",
            continue_on_error=True,
        )
    )
    calls = 0

    def fake_runner(_config: AppConfig, run_id: str | None = None) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated game failure")
        return {
            "run_id": run_id,
            "result": "Victory" if calls == 1 else "Defeat",
            "game_duration_seconds": float(calls * 10),
            "exception": None,
        }

    summary = run_batch(config, single_runner=fake_runner)

    assert summary["games_requested"] == 3
    assert summary["success_count"] == 2
    assert summary["failure_count"] == 1
    assert summary["victory_count"] == 1
    assert summary["defeat_count"] == 1
    summary_path = Path(str(summary["summary_path"]))
    persisted = json.loads(summary_path.read_text(encoding="utf-8"))
    assert len(persisted["games"]) == 3
    assert "simulated game failure" in persisted["exceptions"][0]["message"]


def test_batch_stops_after_failure_when_configured(tmp_path: Path) -> None:
    config = AppConfig(
        experiment=ExperimentConfig(
            games=4,
            output_root=tmp_path / "runs",
            replay_root=tmp_path / "replays",
            continue_on_error=False,
        )
    )

    def failing_runner(_config: AppConfig, run_id: str | None = None) -> dict[str, object]:
        raise RuntimeError(f"failure in {run_id}")

    summary = run_batch(
        config,
        single_runner=failing_runner,
    )

    assert summary["games_completed"] == 1
    assert summary["failure_count"] == 1
