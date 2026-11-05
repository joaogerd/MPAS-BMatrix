"""Numerical NMC subtraction rejects mismatched scientific dimensions."""
from pathlib import Path

import numpy as np
import pytest

from bmatrix.bflow_core.diff import diff_file
from bmatrix.errors import ArtifactError


def _forecast(path: Path, *, ncells: int, nlevels: int, reverse_axes: bool = False,
              value: float = 3.0) -> None:
    netcdf4 = pytest.importorskip("netCDF4")
    with netcdf4.Dataset(path, "w") as ds:
        ds.createDimension("Time", 1)
        ds.createDimension("nCells", ncells)
        ds.createDimension("nVertLevels", nlevels)
        ds.createDimension("StrLen", 19)
        dims = ("Time", "nVertLevels", "nCells") if reverse_axes else (
            "Time", "nCells", "nVertLevels"
        )
        t = ds.createVariable("temperature", "f8", dims)
        t[:] = value
        ds.createVariable("xtime", "S1", ("Time", "StrLen"))[:] = np.array(
            [list(b"2027-01-01_00:00:00")], dtype="S1"
        )


@pytest.mark.parametrize("ncells,nlevels", [(3, 2), (7, 5), (11, 9)])
def test_difference_supports_arbitrary_compatible_mesh_and_levels(
    tmp_path: Path, ncells: int, nlevels: int
):
    older, newer, output = [tmp_path / n for n in ("old.nc", "new.nc", "ptb.nc")]
    _forecast(older, ncells=ncells, nlevels=nlevels, value=5)
    _forecast(newer, ncells=ncells, nlevels=nlevels, value=2)
    diff_file(older, newer, output, "2027-01-01_00:00:00")
    with pytest.importorskip("netCDF4").Dataset(output) as ds:
        np.testing.assert_array_equal(ds.variables["temperature"][:], 3)
        assert "xtime" not in ds.variables


@pytest.mark.parametrize("other_cells,other_levels,reverse_axes", [
    (9, 3, False), (7, 4, False), (7, 3, True),
])
def test_difference_rejects_mixed_mesh_vertical_or_axis_layout(
    tmp_path: Path, other_cells: int, other_levels: int, reverse_axes: bool
):
    older, newer, output = [tmp_path / n for n in ("old.nc", "new.nc", "ptb.nc")]
    _forecast(older, ncells=7, nlevels=3)
    _forecast(newer, ncells=other_cells, nlevels=other_levels, reverse_axes=reverse_axes)
    with pytest.raises(ArtifactError, match="dimensões incompatíveis"):
        diff_file(older, newer, output, "2027-01-01_00:00:00")
