from pathlib import Path

import netCDF4
import numpy as np
import pytest

from bmatrix.artifacts import ArtifactError, StageManifest, require_scientific_identity, scientific_identity


def _sources(tmp_path: Path, shift: float = 0.0):
    tmp_path.mkdir(parents=True, exist_ok=True)
    grid = tmp_path / "grid.nc"
    with netCDF4.Dataset(grid, "w") as ds:
        ds.createDimension("nCells", 2)
        lat = ds.createVariable("latCell", "f8", ("nCells",))
        lon = ds.createVariable("lonCell", "f8", ("nCells",))
        lat[:] = [0.1 + shift, 0.2 + shift]
        lon[:] = [1.1, 1.2]
    invariant = tmp_path / "invariant.nc"
    with netCDF4.Dataset(invariant, "w") as ds:
        ds.createDimension("nVertLevelsP1", 3)
        ds.createDimension("nCells", 2)
        zgrid = ds.createVariable("zgrid", "f8", ("nVertLevelsP1", "nCells"))
        zgrid[:] = np.arange(6).reshape(3, 2) + shift
    return grid, invariant


def _config(tmp_path: Path, shift: float = 0.0):
    grid, invariant = _sources(tmp_path, shift)
    return {
        "mesh": {"name": "x1.test", "grid": str(grid), "nvertlevels": 2},
        "static": {"invariant": str(invariant)},
    }


def test_identity_changes_when_geometry_changes(tmp_path):
    first = scientific_identity(_config(tmp_path / "a", 0.0))
    second = scientific_identity(_config(tmp_path / "b", 1.0))
    assert first["horizontal_geometry_sha256"] != second["horizontal_geometry_sha256"]
    assert first["vertical_geometry_sha256"] != second["vertical_geometry_sha256"]


def test_upstream_identity_mismatch_is_rejected(tmp_path):
    expected = scientific_identity(_config(tmp_path / "expected", 0.0))
    other = scientific_identity(_config(tmp_path / "other", 1.0))
    manifest = StageManifest(
        stage="vbal",
        workspace=str(tmp_path),
        metadata={"scientific_identity": other},
    )
    with pytest.raises(ArtifactError, match="Scientific identity mismatch"):
        require_scientific_identity(manifest, expected)


def test_matching_identity_is_accepted(tmp_path):
    identity = scientific_identity(_config(tmp_path / "case", 0.0))
    manifest = StageManifest(
        stage="vbal",
        workspace=str(tmp_path),
        metadata={"scientific_identity": identity},
    )
    require_scientific_identity(manifest, identity)


def test_same_mesh_different_science_has_different_identity(tmp_path):
    config = _config(tmp_path / "same", 0.0)
    config["vbal"] = {"dominant_mode": 1}
    first = scientific_identity(config)
    config["vbal"]["dominant_mode"] = 2
    second = scientific_identity(config)
    assert first["horizontal_geometry_sha256"] == second["horizontal_geometry_sha256"]
    assert first["vertical_geometry_sha256"] == second["vertical_geometry_sha256"]
    assert first["scientific_settings_sha256"] != second["scientific_settings_sha256"]
    manifest = StageManifest(
        stage="vbal", workspace=str(tmp_path),
        metadata={"scientific_identity": first},
    )
    with pytest.raises(ArtifactError, match="Scientific identity mismatch"):
        require_scientific_identity(manifest, second)


def test_old_geometry_only_artifact_remains_compatible_with_warning(tmp_path):
    config = _config(tmp_path / "old", 0.0)
    current = scientific_identity(config)
    legacy = {key: value for key, value in current.items()
              if key != "scientific_settings_sha256"}
    legacy["schema_version"] = 1
    manifest = StageManifest(
        stage="vbal", workspace=str(tmp_path),
        metadata={"scientific_identity": legacy},
    )
    with pytest.warns(FutureWarning, match="geometry-only"):
        require_scientific_identity(manifest, current)
