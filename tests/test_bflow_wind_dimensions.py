"""Synthetic meshes exercise arbitrary cell/vertical lengths and axis order."""

from pathlib import Path

import numpy as np
import pytest

from bmatrix.bflow_core.dimensions import read_wind_level_cell, write_wind_level_cell
from bmatrix.errors import ArtifactError


@pytest.mark.parametrize("dims", [
    ("Time", "nCells", "nVertLevels"),
    ("nVertLevels", "nCells", "Time"),
    ("Time", "nVertLevels", "nCells"),
    ("nCells", "nVertLevels"),
])
@pytest.mark.parametrize("ncells,nlevels", [(7, 2), (11, 5), (3, 9)])
def test_wind_io_respects_metadata_not_array_positions(
    tmp_path: Path, dims: tuple[str, ...], ncells: int, nlevels: int
) -> None:
    netcdf = pytest.importorskip("netCDF4")
    source = tmp_path / "wind.nc"
    expected = np.arange(ncells * nlevels).reshape(nlevels, ncells) / 3.0
    with netcdf.Dataset(source, "w") as dataset:
        dataset.createDimension("Time", 1)
        dataset.createDimension("nCells", ncells)
        dataset.createDimension("nVertLevels", nlevels)
        variable = dataset.createVariable("u", "f8", dims)
        write_wind_level_cell(variable, expected)
    with netcdf.Dataset(source) as dataset:
        actual = read_wind_level_cell(dataset.variables["u"])
    np.testing.assert_allclose(actual, expected, rtol=0, atol=0)


def test_wind_io_rejects_multiple_times_without_silent_first_record(tmp_path: Path):
    netcdf = pytest.importorskip("netCDF4")
    source = tmp_path / "twotimes.nc"
    with netcdf.Dataset(source, "w") as dataset:
        dataset.createDimension("Time", 2)
        dataset.createDimension("nCells", 8)
        dataset.createDimension("nVertLevels", 3)
        variable = dataset.createVariable("u", "f8", ("Time", "nCells", "nVertLevels"))
        variable[:] = 1.0
        with pytest.raises(ArtifactError, match="exatamente um horário"):
            read_wind_level_cell(variable)


def test_wind_io_rejects_wrong_vertical_or_mesh_dimensions(tmp_path: Path):
    netcdf = pytest.importorskip("netCDF4")
    source = tmp_path / "wrong.nc"
    with netcdf.Dataset(source, "w") as dataset:
        dataset.createDimension("Time", 1)
        dataset.createDimension("nCells", 8)
        dataset.createDimension("nVertLevels", 3)
        variable = dataset.createVariable("u", "f8", ("Time", "nCells", "nVertLevels"))
        with pytest.raises(ArtifactError, match="pesos ESMF"):
            write_wind_level_cell(variable, np.zeros((4, 8)))
        with pytest.raises(ArtifactError, match="pesos ESMF"):
            write_wind_level_cell(variable, np.zeros((3, 7)))


def test_wind_io_rejects_unrelated_vertical_dimension(tmp_path: Path):
    netcdf = pytest.importorskip("netCDF4")
    with netcdf.Dataset(tmp_path / "edge.nc", "w") as dataset:
        dataset.createDimension("nEdges", 8)
        dataset.createDimension("nVertLevels", 3)
        variable = dataset.createVariable("u", "f8", ("nVertLevels", "nEdges"))
        with pytest.raises(ArtifactError, match="nCells e nVertLevels"):
            read_wind_level_cell(variable)
