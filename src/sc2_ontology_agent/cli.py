from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from loguru import logger

from sc2_ontology_agent.config import ConfigError, load_config
from sc2_ontology_agent.environment import collect_environment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sc2-agent",
        description="Ontology SC2 Agent V0.1 experiment runner",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check-env", help="检查 Python、SC2、地图和输出路径")
    check.add_argument("--config", type=Path, default=Path("configs/dev.yaml"))
    for command in ("run", "batch"):
        child = commands.add_parser(command)
        child.add_argument("--config", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "check-env":
        report = collect_environment(args.config)
        print(report.render())
        return 0 if report.ok else 1

    try:
        config = load_config(args.config)
    except ConfigError as error:
        print(f"配置错误: {error}", file=sys.stderr)
        return 2
    _configure_logging(config.logging.log_level)

    if args.command == "run":
        from sc2_ontology_agent.runner import GameRunError, run_single_game

        try:
            metrics = run_single_game(config)
        except GameRunError as error:
            run_directory = config.experiment.output_root / error.run_id
            print(
                f"对局失败: {error}\n已保存可用诊断工件: {run_directory}",
                file=sys.stderr,
            )
            return 1
        print(f"对局完成: {metrics['result']}，run_id={metrics['run_id']}")
        return 0

    from sc2_ontology_agent.runner import run_batch

    summary = run_batch(config)
    print(
        "批次完成: "
        f"成功 {summary['success_count']}，失败 {summary['failure_count']}，"
        f"汇总 {summary['summary_path']}"
    )
    return 0 if summary["failure_count"] == 0 else 1


def _configure_logging(level: str) -> None:
    """Apply the validated YAML level to BurnySc2's Loguru logger."""

    logger.remove()
    logger.add(sys.stderr, level=level)
