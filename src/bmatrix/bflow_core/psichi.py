"""Wind-to-streamfunction/velocity-potential transform for BFLOW."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Mapping

import netCDF4
import numpy as np

from ..errors import ArtifactError, ConfigurationError
from .external import require_files
from .dimensions import read_wind_level_cell, write_wind_level_cell
from .model import BflowPair, compact_time, product_name
from .weights import apply_esmf_weights, load_esmf_sparse_weights, weight_paths


def _require_windspharm():
    try:
        from windspharm.standard import VectorWind
    except ImportError as exc:
        raise ArtifactError(
            "O backend Python psi/chi requer windspharm. "
            "Instale via conda-forge: conda install -c conda-forge windspharm pyspharm"
        ) from exc
    return VectorWind


def _shape_from_weights(weights, regridding: Mapping[str, object]) -> tuple[int, int]:
    dimensions = weights.dst_grid_dims or weights.src_grid_dims
    if len(dimensions) >= 2:
        return int(dimensions[1]), int(dimensions[0])
    resolution = float(regridding["resolution_deg"])
    lower = regridding["lower_left"]
    upper = regridding["upper_right"]
    if not isinstance(lower, list) or not isinstance(upper, list) or len(lower) != 2 or len(upper) != 2:
        raise ConfigurationError("bflow.regridding lower_left/upper_right devem ter dois valores.")
    nlat = round((float(upper[0]) - float(lower[0])) / resolution) + 1
    nlon = round((float(upper[1]) - float(lower[1])) / resolution) + 1
    if nlat < 2 or nlon < 2 or nlat * nlon not in {weights.src_size, weights.dst_size}:
        raise ArtifactError("Metadados dos pesos ESMF não coincidem com a grade auxiliar configurada.")
    return nlat, nlon


def _flat_to_latlon(values: np.ndarray, nlat: int, nlon: int) -> np.ndarray:
    return values.reshape((values.shape[0], nlat, nlon))


def _latlon_to_flat(values: np.ndarray) -> np.ndarray:
    return values.reshape((values.shape[0], values.shape[1] * values.shape[2]))


def uv_to_psichi_windspharm(u_latlon: np.ndarray, v_latlon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Calculate streamfunction and velocity potential on a regular grid."""
    vector_wind = _require_windspharm()
    if u_latlon.shape != v_latlon.shape or u_latlon.ndim != 3:
        raise ValueError("u/v devem ter a mesma forma (nlev, nlat, nlon).")
    u_for_wind = np.transpose(u_latlon[:, ::-1, :], (1, 2, 0))
    v_for_wind = np.transpose(v_latlon[:, ::-1, :], (1, 2, 0))
    psi, chi = vector_wind(u_for_wind, v_for_wind, gridtype="regular").sfvp()
    return (
        np.transpose(np.asarray(psi), (2, 0, 1))[:, ::-1, :],
        np.transpose(np.asarray(chi), (2, 0, 1))[:, ::-1, :],
    )


def _wind_transform(config: Mapping[str, object]) -> Mapping[str, object]:
    bflow = config.get("bflow")
    if not isinstance(bflow, Mapping) or not isinstance(bflow.get("wind_transform"), Mapping):
        raise ConfigurationError("bflow.wind_transform deve ser um bloco YAML.")
    return bflow["wind_transform"]


def write_full_file(
    config: Mapping[str, object],
    template: Path,
    output_path: Path,
    psi_mpas: np.ndarray,
    chi_mpas: np.ndarray,
) -> None:
    """Copy the template and write configured control-variable fields."""
    output_path.unlink(missing_ok=True)
    shutil.copy2(template, output_path)
    transform = _wind_transform(config)
    outputs = transform.get("outputs")
    if not isinstance(outputs, Mapping):
        raise ConfigurationError("bflow.wind_transform.outputs deve ser um bloco YAML.")
    radius_ratio = float(transform.get("radius_numerator_m", 6_371_229.0)) / float(
        transform.get("radius_denominator_m", 6_371_220.0)
    )
    data_by_key = {"stream_function": psi_mpas, "velocity_potential": chi_mpas}
    with netCDF4.Dataset(output_path, "a") as dataset:
        for key, data in data_by_key.items():
            metadata = outputs.get(key)
            if not isinstance(metadata, Mapping):
                raise ConfigurationError(f"Output wind_transform ausente: {key}")
            name = str(metadata.get("file", key))
            if name not in dataset.variables:
                raise ArtifactError(f"Variável ausente no template: {name}")
            variable = dataset.variables[name]
            write_wind_level_cell(
                variable, data * float(metadata.get("scale", 1.0)) * radius_ratio
            )
            variable.setncattr("long_name", str(metadata.get("long_name", key)))
            variable.setncattr("units", str(metadata.get("units", "m^2 s^(-2)")))
            variable.setncattr("bflow_python_backend", "windspharm_esmf_sparse_weights")


def convert_file(
    config: Mapping[str, object],
    input_path: Path,
    output_path: Path,
    template: Path,
    mpas_to_latlon_weights,
    latlon_to_mpas_weights,
) -> None:
    """Transform one MPAS forecast into one configured BFLOW FULL product."""
    require_files([input_path, template], "psi/chi windspharm")
    bflow = config["bflow"]
    regridding = bflow["regridding"]  # type: ignore[index]
    transform = _wind_transform(config)
    nlat, nlon = _shape_from_weights(mpas_to_latlon_weights, regridding)
    zonal = str(transform.get("zonal_file_variable", "uReconstructZonal"))
    meridional = str(transform.get("meridional_file_variable", "uReconstructMeridional"))
    with netCDF4.Dataset(input_path) as dataset:
        if zonal not in dataset.variables or meridional not in dataset.variables:
            raise ArtifactError(f"Campos de vento ausentes em {input_path}: {zonal}, {meridional}")
        u_cell = read_wind_level_cell(dataset.variables[zonal])
        v_cell = read_wind_level_cell(dataset.variables[meridional])
        if u_cell.shape != v_cell.shape:
            raise ArtifactError(
                f"Os campos de vento da previsão {input_path} têm dimensões "
                f"incompatíveis: {zonal}={u_cell.shape}, {meridional}={v_cell.shape}."
            )
    u_latlon = _flat_to_latlon(apply_esmf_weights(u_cell, mpas_to_latlon_weights), nlat, nlon)
    v_latlon = _flat_to_latlon(apply_esmf_weights(v_cell, mpas_to_latlon_weights), nlat, nlon)
    psi_latlon, chi_latlon = uv_to_psichi_windspharm(u_latlon, v_latlon)
    write_full_file(
        config,
        template,
        output_path,
        apply_esmf_weights(_latlon_to_flat(psi_latlon), latlon_to_mpas_weights),
        apply_esmf_weights(_latlon_to_flat(chi_latlon), latlon_to_mpas_weights),
    )


def convert_pair(config: Mapping[str, object], workspace: str | Path, pair: BflowPair) -> None:
    """Create both FULL products for one NMC pair."""
    root = Path(workspace).resolve()
    mpas_to_latlon, latlon_to_mpas = weight_paths(config, root)
    mpas_to_latlon_weights = load_esmf_sparse_weights(mpas_to_latlon)
    latlon_to_mpas_weights = load_esmf_sparse_weights(latlon_to_mpas)
    template = root / product_name(config, "template")
    directory = root / "output" / compact_time(pair.valid_time)
    directory.mkdir(parents=True, exist_ok=True)
    for source, output in ((pair.f048, directory / product_name(config, "older_full")), (pair.f024, directory / product_name(config, "newer_full"))):
        convert_file(config, source, output, template, mpas_to_latlon_weights, latlon_to_mpas_weights)


def convert_uv_to_psichi(config: Mapping[str, object], workspace: str | Path, pairs: list[BflowPair]) -> None:
    """Create FULL products for every configured pair."""
    for pair in pairs:
        convert_pair(config, workspace, pair)
