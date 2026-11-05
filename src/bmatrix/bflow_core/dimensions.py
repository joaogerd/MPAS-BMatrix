"""Dimension-aware MPAS wind I/O shared by BFLOW forecast conversion.

The scientific array convention is (vertical_level, cell). NetCDF variable
dimension ordering is metadata, not an implicit part of the operation.
"""
from __future__ import annotations

import numpy as np

from ..errors import ArtifactError

_WIND_AXES = ("nVertLevels", "nCells")


def _active_axes(variable) -> tuple[tuple[object, ...], tuple[str, ...]]:
    index = []
    active = []
    for axis, name in enumerate(variable.dimensions):
        if name in {"Time", "time"}:
            if variable.shape[axis] != 1:
                raise ArtifactError(
                    f"O campo {variable.name} contém {variable.shape[axis]} tempos. "
                    "Forneça um estado MPAS com exatamente um horário válido."
                )
            index.append(0)
        else:
            index.append(slice(None))
            active.append(name)
    if set(active) != set(_WIND_AXES) or len(active) != 2:
        raise ArtifactError(
            f"O campo {variable.name} usa dimensões {variable.dimensions!r}. "
            "Os ventos para BFLOW precisam conter nCells e nVertLevels, "
            "com Time opcional de comprimento 1."
        )
    return tuple(index), tuple(active)


def read_wind_level_cell(variable) -> np.ndarray:
    """Return float64 wind values in (nVertLevels, nCells) order."""
    index, active = _active_axes(variable)
    values = np.asarray(variable[index], dtype=np.float64)
    if values.ndim != 2:
        raise ArtifactError(f"O campo {variable.name} não contém um array 2D espacial.")
    if active == ("nCells", "nVertLevels"):
        return values.T
    return values


def write_wind_level_cell(variable, data: np.ndarray) -> None:
    """Write (nVertLevels,nCells) winds into the variable's declared axes."""
    index, active = _active_axes(variable)
    values = np.asarray(data)
    nlevels = variable.shape[variable.dimensions.index("nVertLevels")]
    ncells = variable.shape[variable.dimensions.index("nCells")]
    if values.shape != (nlevels, ncells):
        raise ArtifactError(
            f"Vento calculado para {variable.name} tem forma {values.shape}, "
            f"mas o template NetCDF requer ({nlevels}, {ncells}). "
            "Verifique a malha, o número de níveis e os pesos ESMF."
        )
    variable[index] = values.T if active == ("nCells", "nVertLevels") else values
