from pathlib import Path

from sc2_ontology_agent.environment import discover_sc2_install


def test_sc2path_environment_variable_selects_maps_directory(
    tmp_path: Path, monkeypatch: object
) -> None:
    install = tmp_path / "StarCraft II"
    (install / "Versions" / "Base12345").mkdir(parents=True)
    maps = install / "Maps"
    maps.mkdir()
    (maps / "AcropolisLE.SC2Map").write_bytes(b"test-map")
    monkeypatch.setenv("SC2PATH", str(install))  # type: ignore[attr-defined]

    detected_install, detected_maps = discover_sc2_install()

    assert detected_install == install
    assert detected_maps == maps
