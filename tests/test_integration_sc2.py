import os
from pathlib import Path

import pytest

from sc2_ontology_agent.config import load_config
from sc2_ontology_agent.runner import run_single_game


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_SC2_INTEGRATION") != "1",
    reason="Set RUN_SC2_INTEGRATION=1 only when SC2 and AcropolisLE are installed.",
)
def test_real_sc2_game_completes_and_writes_artifacts() -> None:
    metrics = run_single_game(load_config(Path("configs/dev.yaml")))
    assert metrics["result"] in {"Victory", "Defeat", "Tie"}
    assert Path(str(metrics["replay_path"])).is_file()
