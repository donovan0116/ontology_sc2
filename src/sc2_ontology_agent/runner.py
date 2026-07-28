from __future__ import annotations

import json
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any
from uuid import uuid4

from sc2 import maps
from sc2.data import Difficulty, Race
from sc2.main import run_game
from sc2.player import Bot, Computer

from sc2_ontology_agent.bot import OntologySc2Bot
from sc2_ontology_agent.config import AppConfig, ConfigError, save_config, validate_identifier
from sc2_ontology_agent.environment import discover_sc2_install, map_exists
from sc2_ontology_agent.logging.event_logger import EventLogger
from sc2_ontology_agent.logging.metrics import MetricsCollector
from sc2_ontology_agent.policy.simple_rule_policy import SimpleRulePolicy

MetricsDocument = dict[str, Any]
SingleRunner = Callable[[AppConfig, str | None], MetricsDocument]


class GameRunError(RuntimeError):
    """Raised after a failed game has persisted all available artifacts."""

    def __init__(self, run_id: str, metrics: MetricsDocument, message: str) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.metrics = metrics


def make_run_id(run_name: str, *, suffix: str | None = None) -> str:
    validate_identifier(run_name, "run_name")
    if suffix is not None:
        validate_identifier(suffix, "run_id suffix")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    parts = [run_name, timestamp]
    if suffix:
        parts.append(suffix)
    parts.append(uuid4().hex[:8])
    return "-".join(parts)


def run_single_game(config: AppConfig, run_id: str | None = None) -> MetricsDocument:
    """Run one built-in-AI game and persist config, events, metrics, error, and replay."""

    actual_run_id = run_id or make_run_id(config.experiment.run_name)
    try:
        validate_identifier(actual_run_id, "run_id")
    except ConfigError as error:
        raise ValueError(str(error)) from error
    run_directory = config.experiment.output_root / actual_run_id
    run_directory.mkdir(parents=True, exist_ok=False)
    save_config(config, run_directory / "config.yaml")
    config.experiment.replay_root.mkdir(parents=True, exist_ok=True)
    replay_path = (
        config.experiment.replay_root / f"{actual_run_id}.SC2Replay"
        if config.game.save_replay
        else None
    )
    event_logger = EventLogger(
        run_directory / "events.jsonl",
        actual_run_id,
        enabled=config.logging.event_log_enabled,
    )
    metrics_collector = MetricsCollector(actual_run_id)
    bot_ai = OntologySc2Bot(
        bot_config=config.bot,
        game_config=config.game,
        logging_config=config.logging,
        advisor=SimpleRulePolicy(config.bot),
        event_logger=event_logger,
        metrics=metrics_collector,
        metrics_path=run_directory / "metrics.json",
        replay_path=replay_path,
    )
    try:
        install, maps_directory = discover_sc2_install()
        if install is None:
            raise RuntimeError(
                "StarCraft II installation not found. Install SC2 or set SC2PATH "
                "to the installation directory."
            )
        if maps_directory is None:
            raise RuntimeError(
                f"StarCraft II maps directory not found under {install}. "
                "Create Maps and add the configured map manually."
            )
        if not map_exists(maps_directory, config.game.map_name):
            raise RuntimeError(
                f"SC2 map not found: {config.game.map_name}. Expected "
                f"{config.game.map_name}.SC2Map in {maps_directory} or one subdirectory."
            )
        result = run_game(
            maps.get(config.game.map_name),
            [
                Bot(_race(config.player.race), bot_ai),
                Computer(
                    _race(config.opponent.race),
                    _difficulty(config.opponent.difficulty),
                ),
            ],
            realtime=config.game.realtime,
            save_replay_as=str(replay_path) if replay_path is not None else None,
        )
        if bot_ai.fatal_error is not None:
            fatal_error = bot_ai.fatal_error
            metrics = bot_ai.finalize_exception(fatal_error)
            _write_error(run_directory / "error.json", actual_run_id, fatal_error)
            raise GameRunError(actual_run_id, metrics, str(fatal_error)) from fatal_error
        final_metrics = bot_ai.final_metrics
        if final_metrics is None:
            raise RuntimeError(f"game returned {result!r} without invoking bot.on_end")
        return final_metrics
    except GameRunError:
        raise
    except Exception as error:
        metrics = bot_ai.finalize_exception(error)
        _write_error(run_directory / "error.json", actual_run_id, error)
        raise GameRunError(actual_run_id, metrics, str(error)) from error
    finally:
        event_logger.close()


def run_batch(
    config: AppConfig,
    single_runner: SingleRunner | None = None,
) -> MetricsDocument:
    """Run sequential independent games and always persist the completed batch prefix."""

    runner = single_runner or run_single_game
    batch_id = make_run_id(f"{config.experiment.run_name}-batch")
    batch_directory = config.experiment.output_root / batch_id
    batch_directory.mkdir(parents=True, exist_ok=False)
    save_config(config, batch_directory / "config.yaml")
    games: list[MetricsDocument] = []
    exceptions: list[dict[str, str]] = []

    for index in range(1, config.experiment.games + 1):
        run_id = make_run_id(config.experiment.run_name, suffix=f"g{index:03d}")
        try:
            metrics = runner(config, run_id)
            games.append(
                {
                    "run_id": run_id,
                    "status": "success",
                    **metrics,
                }
            )
        except GameRunError as error:
            games.append(
                {
                    "run_id": error.run_id,
                    "status": "failed",
                    **error.metrics,
                }
            )
            exceptions.append(
                {
                    "run_id": error.run_id,
                    "type": type(error.__cause__).__name__
                    if error.__cause__
                    else type(error).__name__,
                    "message": str(error),
                }
            )
            if not config.experiment.continue_on_error:
                break
        except Exception as error:
            games.append(
                {
                    "run_id": run_id,
                    "status": "failed",
                    "result": "Error",
                    "exception": f"{type(error).__name__}: {error}",
                }
            )
            exceptions.append(
                {
                    "run_id": run_id,
                    "type": type(error).__name__,
                    "message": str(error),
                }
            )
            if not config.experiment.continue_on_error:
                break
        summary = _batch_summary(batch_id, config.experiment.games, games, exceptions)
        _write_json(summary, batch_directory / "batch-summary.json")

    summary = _batch_summary(batch_id, config.experiment.games, games, exceptions)
    summary_path = batch_directory / "batch-summary.json"
    summary["summary_path"] = str(summary_path)
    _write_json(summary, summary_path)
    return summary


def _batch_summary(
    batch_id: str,
    games_requested: int,
    games: list[MetricsDocument],
    exceptions: list[dict[str, str]],
) -> MetricsDocument:
    successful = [game for game in games if game["status"] == "success"]
    durations = [
        float(game["game_duration_seconds"])
        for game in successful
        if isinstance(game.get("game_duration_seconds"), int | float)
    ]
    return {
        "batch_id": batch_id,
        "games_requested": games_requested,
        "games_completed": len(games),
        "success_count": len(successful),
        "failure_count": len(games) - len(successful),
        "victory_count": sum(game.get("result") == "Victory" for game in successful),
        "defeat_count": sum(game.get("result") == "Defeat" for game in successful),
        "tie_count": sum(game.get("result") == "Tie" for game in successful),
        "average_game_duration_seconds": round(fmean(durations), 3) if durations else None,
        "exceptions": exceptions,
        "games": games,
    }


def _race(name: str) -> Race:
    try:
        return Race[name]
    except KeyError as error:
        raise ValueError(f"unsupported SC2 race: {name}") from error


def _difficulty(name: str) -> Difficulty:
    try:
        return Difficulty[name]
    except KeyError as error:
        raise ValueError(f"unsupported SC2 difficulty: {name}") from error


def _write_error(path: Path, run_id: str, error: Exception) -> None:
    _write_json(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "run_id": run_id,
            "exception_type": type(error).__name__,
            "message": str(error),
            "traceback": "".join(traceback.format_exception(error)),
        },
        path,
    )


def _write_json(document: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
