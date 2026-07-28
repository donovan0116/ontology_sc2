from __future__ import annotations

import importlib.metadata
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from sc2_ontology_agent.config import AppConfig, ConfigError, load_config


@dataclass(frozen=True, slots=True)
class EnvironmentCheck:
    name: str
    ok: bool
    value: str
    fix: str | None = None


@dataclass(frozen=True, slots=True)
class EnvironmentReport:
    checks: tuple[EnvironmentCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def render(self) -> str:
        lines: list[str] = []
        for check in self.checks:
            marker = "OK" if check.ok else "MISSING"
            lines.append(f"[{marker}] {check.name}: {check.value}")
            if not check.ok and check.fix:
                lines.append(f"         修复: {check.fix}")
        lines.append(f"\n总体状态: {'可运行真实对局' if self.ok else '环境尚不完整'}")
        return "\n".join(lines)


def discover_sc2_install() -> tuple[Path | None, Path | None]:
    """Find an SC2 base and maps directory without triggering BurnySc2's sys.exit."""

    candidates: list[Path] = []
    configured = os.environ.get("SC2PATH")
    if configured:
        candidates.append(Path(configured).expanduser())
    system = platform.system()
    if system == "Darwin":
        candidates.append(Path("/Applications/StarCraft II"))
    elif system == "Windows":
        candidates.append(Path("C:/Program Files (x86)/StarCraft II"))
    else:
        candidates.extend(
            [
                Path("~/StarCraftII").expanduser(),
                Path("~/.wine/drive_c/Program Files (x86)/StarCraft II").expanduser(),
            ]
        )
    for candidate in candidates:
        if not candidate.is_dir() or not (candidate / "Versions").is_dir():
            continue
        version_directories = [
            child
            for child in (candidate / "Versions").iterdir()
            if child.is_dir() and child.name.startswith("Base")
        ]
        if not version_directories:
            continue
        maps = next(
            (
                child
                for child in candidate.iterdir()
                if child.is_dir() and child.name in {"Maps", "maps"}
            ),
            None,
        )
        return candidate, maps
    return None, None


def collect_environment(config_path: Path = Path("configs/dev.yaml")) -> EnvironmentReport:
    """Collect actionable diagnostics while continuing after each missing component."""

    checks: list[EnvironmentCheck] = [
        EnvironmentCheck(
            "操作系统",
            True,
            f"{platform.system()} {platform.release()} ({platform.machine()})",
        )
    ]
    python_ok = (3, 11) <= sys.version_info[:2] < (3, 15)
    checks.append(
        EnvironmentCheck(
            "Python",
            python_ok,
            platform.python_version(),
            "安装 Python 3.11–3.14；推荐使用 `uv sync` 自动准备 Python 3.11。"
            if not python_ok
            else None,
        )
    )
    try:
        burnysc2_version = importlib.metadata.version("burnysc2")
        package_ok = burnysc2_version == "7.3.0"
        package_value = burnysc2_version
    except importlib.metadata.PackageNotFoundError:
        package_ok = False
        package_value = "未安装"
    checks.append(
        EnvironmentCheck(
            "python-sc2 包（burnysc2）",
            package_ok,
            package_value,
            "运行 `uv sync` 或 `python -m pip install -e '.[dev]'`。" if not package_ok else None,
        )
    )

    config: AppConfig | None
    try:
        config = load_config(config_path)
        checks.append(EnvironmentCheck("配置文件", True, str(config_path)))
    except ConfigError as error:
        config = None
        checks.append(
            EnvironmentCheck(
                "配置文件",
                False,
                str(error),
                f"修正配置后重试：{config_path}",
            )
        )

    install, maps = discover_sc2_install()
    checks.append(
        EnvironmentCheck(
            "StarCraft II 路径",
            install is not None,
            str(install) if install else "未识别",
            "通过 Battle.net 安装 SC2；非默认位置请设置环境变量 SC2PATH。"
            if install is None
            else None,
        )
    )
    checks.append(
        EnvironmentCheck(
            "地图目录",
            maps is not None,
            str(maps) if maps else "不存在",
            "在 SC2 安装目录创建 Maps，并手动放入合法取得的 .SC2Map 文件。"
            if maps is None
            else None,
        )
    )
    if config is not None:
        map_found = maps is not None and map_exists(maps, config.game.map_name)
        checks.append(
            EnvironmentCheck(
                "配置地图",
                map_found,
                config.game.map_name,
                (
                    f"将 {config.game.map_name}.SC2Map 放入 {maps or '<SC2>/Maps'}"
                    "（BurnySc2 最多搜索一层子目录）。"
                    if not map_found
                    else None
                ),
            )
        )
        checks.extend(
            [
                _writable_check("运行输出目录", config.experiment.output_root),
                _writable_check("回放输出目录", config.experiment.replay_root),
            ]
        )
    return EnvironmentReport(tuple(checks))


def map_exists(maps: Path, map_name: str) -> bool:
    """Match BurnySc2's exact file-name and one-subdirectory map lookup."""

    direct = maps / f"{map_name}.SC2Map"
    if direct.is_file():
        return True
    return any(candidate.is_file() for candidate in maps.glob(f"*/{map_name}.SC2Map"))


def _writable_check(name: str, directory: Path) -> EnvironmentCheck:
    probe = directory / f".sc2-agent-write-check-{uuid4().hex}"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as error:
        return EnvironmentCheck(
            name,
            False,
            f"{directory}: {error}",
            "修改目录权限或在 experiment 中选择可写目录。",
        )
    return EnvironmentCheck(name, True, str(directory))
