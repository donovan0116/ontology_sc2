# Repository Guidelines

## Project Structure & Module Organization

Production code uses a `src` layout under `src/sc2_ontology_agent/`. Keep framework-independent values in `domain/`, tactical recommendations in `policy/`, BurnySc2 command translation in `execution/`, and structured experiment output in `logging/`. `bot.py` is the thin SC2 lifecycle adapter; `runner.py` owns single-game and batch orchestration; `cli.py` exposes commands.

Tests live in `tests/` and should mirror the behavior they protect. Runtime examples are in `configs/dev.yaml` and `configs/batch.yaml`. Architecture and data semantics are documented in `docs/`. Generated artifacts belong in `runs/` and `replays/`; do not commit them.

## Build, Test, and Development Commands

Use Python 3.11 and the checked-in lock file:

```bash
uv sync
python -m sc2_ontology_agent check-env
python -m sc2_ontology_agent run --config configs/dev.yaml
python -m sc2_ontology_agent batch --config configs/batch.yaml
```

Run all quality gates before submitting changes:

```bash
pytest
ruff check .
ruff format --check .
mypy src
```

Use `ruff format .` to apply formatting.

## Coding Style & Naming Conventions

Use four-space indentation and complete type annotations for public interfaces. Follow standard Python naming: `snake_case` for modules, functions, and variables; `PascalCase` for classes; uppercase names for enums and constants. Keep SC2 `Unit`, `Units`, tags, and `Point2` objects out of domain models. Prefer small delegated methods over expanding `on_step()`. Put gameplay thresholds in typed YAML configuration, not magic numbers.

## Testing Guidelines

Pytest is the test framework. Name files `test_<module>.py` and tests `test_<observable_behavior>`. Test policies with `GameSnapshot` values rather than a real SC2 client. Every bug fix should first reproduce the failure, then verify the correction. Real-game tests are opt-in:

```bash
RUN_SC2_INTEGRATION=1 pytest -m integration -v
```

Never report integration success unless SC2 actually launched and produced results.

## Commit & Pull Request Guidelines

No Git history is present to establish an existing convention. Use concise Conventional Commit-style subjects, such as `feat: add marine reinforcement rule` or `fix: preserve failed batch metrics`. Pull requests should explain behavior changes, list verification commands and results, link relevant issues, and call out configuration or artifact-format changes. Include screenshots only when they materially clarify SC2 output or documentation rendering.

## Security & Configuration Tips

Do not download or commit StarCraft II binaries, maps, replays, credentials, or machine-specific paths. Use `SC2PATH` for non-default installations and keep committed YAML portable.
