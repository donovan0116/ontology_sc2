from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when a YAML configuration is unknown, malformed, or invalid."""


@dataclass(frozen=True, slots=True)
class GameConfig:
    map_name: str = "AcropolisLE"
    realtime: bool = False
    game_step: int = 8
    save_replay: bool = True


@dataclass(frozen=True, slots=True)
class PlayerConfig:
    race: str = "Terran"


@dataclass(frozen=True, slots=True)
class OpponentConfig:
    race: str = "Terran"
    difficulty: str = "Easy"


@dataclass(frozen=True, slots=True)
class BotConfig:
    policy: str = "hierarchical"
    worker_limit: int = 44
    attack_marine_threshold: int = 10
    supply_buffer: int = 6
    max_barracks: int = 2
    decision_interval_steps: int = 4
    build_search_radius: int = 20
    building_spacing: int = 7
    expansion_worker_threshold: int = 20
    scout_start_time_seconds: int = 90
    attack_army_supply: int = 24
    reinforcement_army_supply: int = 8
    marine_to_marauder_ratio: int = 2
    defense_radius: int = 30
    rally_map_fraction: float = 0.35
    task_retry_limit: int = 3
    task_retry_cooldown_steps: int = 2
    task_timeout_seconds: int = 120


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    run_name: str = "dev"
    games: int = 1
    output_root: Path = Path("runs")
    replay_root: Path = Path("replays")
    continue_on_error: bool = True


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    event_log_enabled: bool = True
    snapshot_interval_steps: int = 16
    log_level: str = "INFO"


@dataclass(frozen=True, slots=True)
class AppConfig:
    game: GameConfig = field(default_factory=GameConfig)
    player: PlayerConfig = field(default_factory=PlayerConfig)
    opponent: OpponentConfig = field(default_factory=OpponentConfig)
    bot: BotConfig = field(default_factory=BotConfig)
    experiment: ExperimentConfig = field(default_factory=ExperimentConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        experiment = data["experiment"]
        experiment["output_root"] = str(experiment["output_root"])
        experiment["replay_root"] = str(experiment["replay_root"])
        return data


class _StrictSafeLoader(yaml.SafeLoader):
    pass


_StrictSafeLoader.yaml_implicit_resolvers = {
    key: list(value) for key, value in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
for resolver_key, resolvers in _StrictSafeLoader.yaml_implicit_resolvers.items():
    _StrictSafeLoader.yaml_implicit_resolvers[resolver_key] = [
        item for item in resolvers if item[0] != "tag:yaml.org,2002:bool"
    ]
_StrictSafeLoader.add_implicit_resolver(  # type: ignore[no-untyped-call]  # PyYAML API
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false)$", re.IGNORECASE),
    list("tTfF"),
)

_SECTIONS = {"game", "player", "opponent", "bot", "experiment", "logging"}
_GAME_DEFAULTS = GameConfig()
_PLAYER_DEFAULTS = PlayerConfig()
_OPPONENT_DEFAULTS = OpponentConfig()
_BOT_DEFAULTS = BotConfig()
_EXPERIMENT_DEFAULTS = ExperimentConfig()
_LOGGING_DEFAULTS = LoggingConfig()
_DIFFICULTIES = {
    "VeryEasy",
    "Easy",
    "Medium",
    "MediumHard",
    "Hard",
    "Harder",
    "VeryHard",
    "CheatVision",
    "CheatMoney",
    "CheatInsane",
}
_OPPONENT_RACES = {"Terran", "Zerg", "Protoss", "Random"}
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _mapping(value: object, context: str) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ConfigError(f"{context} must be a YAML mapping")
    return value


def _section(
    root: dict[str, object],
    name: str,
    allowed_fields: set[str],
) -> dict[str, object]:
    values = _mapping(root.get(name), name)
    unknown = set(values) - allowed_fields
    if unknown:
        raise ConfigError(f"{name}: unknown field(s): {', '.join(sorted(unknown))}")
    return values


def _typed(values: dict[str, object], key: str, expected: type[Any], default: Any) -> Any:
    value = values.get(key, default)
    if expected is int and (not isinstance(value, int) or isinstance(value, bool)):
        raise ConfigError(f"{key} must be an integer")
    if expected is float and (not isinstance(value, int | float) or isinstance(value, bool)):
        raise ConfigError(f"{key} must be a number")
    if expected is bool and not isinstance(value, bool):
        raise ConfigError(f"{key} must be true or false")
    if expected is str and not isinstance(value, str):
        raise ConfigError(f"{key} must be a string")
    return value


def _positive(value: int, key: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if value < minimum:
        qualifier = "non-negative" if allow_zero else "positive"
        raise ConfigError(f"{key} must be {qualifier}")
    return value


def validate_identifier(value: str, key: str) -> str:
    """Reject path separators, traversal components, whitespace, and empty names."""

    if value in {".", ".."} or _SAFE_IDENTIFIER.fullmatch(value) is None:
        raise ConfigError(
            f"{key} must be a safe identifier containing only letters, numbers, '.', '_', or '-'"
        )
    return value


def load_config(path: Path) -> AppConfig:
    """Load YAML without silently accepting unknown keys or invalid scalar types."""

    try:
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=_StrictSafeLoader)
    except FileNotFoundError as error:
        raise ConfigError(f"configuration file not found: {path}") from error
    except yaml.YAMLError as error:
        raise ConfigError(f"invalid YAML in {path}: {error}") from error
    root = _mapping(raw, "configuration")
    unknown_sections = set(root) - _SECTIONS
    if unknown_sections:
        raise ConfigError(f"unknown section(s): {', '.join(sorted(unknown_sections))}")

    game_values = _section(root, "game", {"map_name", "realtime", "game_step", "save_replay"})
    game = GameConfig(
        map_name=_typed(game_values, "map_name", str, _GAME_DEFAULTS.map_name),
        realtime=_typed(game_values, "realtime", bool, _GAME_DEFAULTS.realtime),
        game_step=_positive(
            _typed(game_values, "game_step", int, _GAME_DEFAULTS.game_step),
            "game_step",
        ),
        save_replay=_typed(game_values, "save_replay", bool, _GAME_DEFAULTS.save_replay),
    )
    if not game.map_name.strip():
        raise ConfigError("map_name must not be empty")

    player_values = _section(root, "player", {"race"})
    player = PlayerConfig(race=_typed(player_values, "race", str, _PLAYER_DEFAULTS.race))
    if player.race != "Terran":
        raise ConfigError("player race must be Terran in V0.1")

    opponent_values = _section(root, "opponent", {"race", "difficulty"})
    opponent = OpponentConfig(
        race=_typed(opponent_values, "race", str, _OPPONENT_DEFAULTS.race),
        difficulty=_typed(
            opponent_values,
            "difficulty",
            str,
            _OPPONENT_DEFAULTS.difficulty,
        ),
    )
    if opponent.race not in _OPPONENT_RACES:
        raise ConfigError(f"unsupported opponent race: {opponent.race}")
    if opponent.difficulty not in _DIFFICULTIES:
        raise ConfigError(f"unsupported opponent difficulty: {opponent.difficulty}")

    bot_values = _section(
        root,
        "bot",
        {
            "policy",
            "worker_limit",
            "attack_marine_threshold",
            "supply_buffer",
            "max_barracks",
            "decision_interval_steps",
            "build_search_radius",
            "building_spacing",
            "expansion_worker_threshold",
            "scout_start_time_seconds",
            "attack_army_supply",
            "reinforcement_army_supply",
            "marine_to_marauder_ratio",
            "defense_radius",
            "rally_map_fraction",
            "task_retry_limit",
            "task_retry_cooldown_steps",
            "task_timeout_seconds",
        },
    )
    bot = BotConfig(
        policy=_typed(bot_values, "policy", str, _BOT_DEFAULTS.policy),
        worker_limit=_positive(
            _typed(bot_values, "worker_limit", int, _BOT_DEFAULTS.worker_limit),
            "worker_limit",
        ),
        attack_marine_threshold=_positive(
            _typed(
                bot_values,
                "attack_marine_threshold",
                int,
                _BOT_DEFAULTS.attack_marine_threshold,
            ),
            "attack_marine_threshold",
        ),
        supply_buffer=_positive(
            _typed(bot_values, "supply_buffer", int, _BOT_DEFAULTS.supply_buffer),
            "supply_buffer",
            allow_zero=True,
        ),
        max_barracks=_positive(
            _typed(bot_values, "max_barracks", int, _BOT_DEFAULTS.max_barracks),
            "max_barracks",
        ),
        decision_interval_steps=_positive(
            _typed(
                bot_values,
                "decision_interval_steps",
                int,
                _BOT_DEFAULTS.decision_interval_steps,
            ),
            "decision_interval_steps",
        ),
        build_search_radius=_positive(
            _typed(
                bot_values,
                "build_search_radius",
                int,
                _BOT_DEFAULTS.build_search_radius,
            ),
            "build_search_radius",
        ),
        building_spacing=_positive(
            _typed(bot_values, "building_spacing", int, _BOT_DEFAULTS.building_spacing),
            "building_spacing",
        ),
        expansion_worker_threshold=_positive(
            _typed(
                bot_values,
                "expansion_worker_threshold",
                int,
                _BOT_DEFAULTS.expansion_worker_threshold,
            ),
            "expansion_worker_threshold",
        ),
        scout_start_time_seconds=_positive(
            _typed(
                bot_values,
                "scout_start_time_seconds",
                int,
                _BOT_DEFAULTS.scout_start_time_seconds,
            ),
            "scout_start_time_seconds",
            allow_zero=True,
        ),
        attack_army_supply=_positive(
            _typed(
                bot_values,
                "attack_army_supply",
                int,
                _BOT_DEFAULTS.attack_army_supply,
            ),
            "attack_army_supply",
        ),
        reinforcement_army_supply=_positive(
            _typed(
                bot_values,
                "reinforcement_army_supply",
                int,
                _BOT_DEFAULTS.reinforcement_army_supply,
            ),
            "reinforcement_army_supply",
        ),
        marine_to_marauder_ratio=_positive(
            _typed(
                bot_values,
                "marine_to_marauder_ratio",
                int,
                _BOT_DEFAULTS.marine_to_marauder_ratio,
            ),
            "marine_to_marauder_ratio",
        ),
        defense_radius=_positive(
            _typed(bot_values, "defense_radius", int, _BOT_DEFAULTS.defense_radius),
            "defense_radius",
        ),
        rally_map_fraction=_typed(
            bot_values,
            "rally_map_fraction",
            float,
            _BOT_DEFAULTS.rally_map_fraction,
        ),
        task_retry_limit=_positive(
            _typed(bot_values, "task_retry_limit", int, _BOT_DEFAULTS.task_retry_limit),
            "task_retry_limit",
            allow_zero=True,
        ),
        task_retry_cooldown_steps=_positive(
            _typed(
                bot_values,
                "task_retry_cooldown_steps",
                int,
                _BOT_DEFAULTS.task_retry_cooldown_steps,
            ),
            "task_retry_cooldown_steps",
            allow_zero=True,
        ),
        task_timeout_seconds=_positive(
            _typed(
                bot_values,
                "task_timeout_seconds",
                int,
                _BOT_DEFAULTS.task_timeout_seconds,
            ),
            "task_timeout_seconds",
        ),
    )
    if bot.policy not in {"simple", "hierarchical"}:
        raise ConfigError(f"unsupported policy: {bot.policy}")
    if bot.policy == "hierarchical" and bot.max_barracks < 2:
        raise ConfigError("max_barracks must be at least 2 for hierarchical policy")
    if not 0.0 < bot.rally_map_fraction < 1.0:
        raise ConfigError("rally_map_fraction must be between 0 and 1")

    experiment_values = _section(
        root,
        "experiment",
        {
            "run_name",
            "games",
            "output_root",
            "replay_root",
            "continue_on_error",
        },
    )
    run_name = _typed(experiment_values, "run_name", str, _EXPERIMENT_DEFAULTS.run_name)
    validate_identifier(run_name, "run_name")
    experiment = ExperimentConfig(
        run_name=run_name,
        games=_positive(
            _typed(experiment_values, "games", int, _EXPERIMENT_DEFAULTS.games),
            "games",
        ),
        output_root=Path(
            _typed(
                experiment_values,
                "output_root",
                str,
                str(_EXPERIMENT_DEFAULTS.output_root),
            )
        ),
        replay_root=Path(
            _typed(
                experiment_values,
                "replay_root",
                str,
                str(_EXPERIMENT_DEFAULTS.replay_root),
            )
        ),
        continue_on_error=_typed(
            experiment_values,
            "continue_on_error",
            bool,
            _EXPERIMENT_DEFAULTS.continue_on_error,
        ),
    )

    logging_values = _section(
        root,
        "logging",
        {"event_log_enabled", "snapshot_interval_steps", "log_level"},
    )
    logging = LoggingConfig(
        event_log_enabled=_typed(
            logging_values,
            "event_log_enabled",
            bool,
            _LOGGING_DEFAULTS.event_log_enabled,
        ),
        snapshot_interval_steps=_positive(
            _typed(
                logging_values,
                "snapshot_interval_steps",
                int,
                _LOGGING_DEFAULTS.snapshot_interval_steps,
            ),
            "snapshot_interval_steps",
        ),
        log_level=_typed(
            logging_values,
            "log_level",
            str,
            _LOGGING_DEFAULTS.log_level,
        ).upper(),
    )
    if logging.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError(f"unsupported log_level: {logging.log_level}")

    return AppConfig(game, player, opponent, bot, experiment, logging)


def save_config(config: AppConfig, path: Path) -> None:
    """Persist the exact effective configuration for reproducible runs."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(config.to_dict(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
