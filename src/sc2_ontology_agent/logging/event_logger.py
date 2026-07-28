from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from sc2_ontology_agent.domain.intent import MacroIntent
from sc2_ontology_agent.domain.records import ExecutionResult
from sc2_ontology_agent.domain.state import GameSnapshot


class EventLogger:
    """Append-only UTF-8 JSON Lines writer that flushes every durable event."""

    def __init__(self, path: Path, run_id: str, enabled: bool = True) -> None:
        self._path = path
        self._run_id = run_id
        self._enabled = enabled
        self._stream: TextIO | None = None
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._stream = path.open("a", encoding="utf-8")

    def log(
        self,
        event_type: str,
        *,
        snapshot: GameSnapshot | None = None,
        intent: MacroIntent | None = None,
        execution: ExecutionResult | None = None,
        details: dict[str, object] | None = None,
        game_loop: int | None = None,
        game_time_seconds: float | None = None,
    ) -> None:
        if self._stream is None:
            return
        record: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "run_id": self._run_id,
            "game_loop": snapshot.game_loop if snapshot is not None else (game_loop or 0),
            "game_time_seconds": (
                snapshot.game_time_seconds if snapshot is not None else (game_time_seconds or 0.0)
            ),
            "event_type": event_type,
        }
        if snapshot is not None:
            record["snapshot"] = snapshot.to_dict()
        if intent is not None:
            record["intent"] = intent.to_dict()
        if execution is not None:
            record["execution"] = execution.to_dict()
        if details is not None:
            record["details"] = details
        self._stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._stream.flush()

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    def __enter__(self) -> EventLogger:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
