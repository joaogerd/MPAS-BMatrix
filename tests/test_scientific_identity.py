from pathlib import Path

import netCDF4
import numpy as np
import pytest

from bmatrix.artifacts import ArtifactError, StageManifest, require_scientific_identity, scientific_identity


def _sources(tmp_path: Path, shift: float = 0.0):
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
