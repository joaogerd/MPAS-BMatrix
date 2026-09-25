"""NICAS split/merge input rendering from the scientific configuration."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

import yaml

from ..scheduler import bmatrix_job_spec, mpi_command, render_pbs
from ..scientific_config import control_file_names, normalize_control, section
from ..shell import write_text
from ..vbal_core.model import toolbox_exe


def _dirac_points(config: Mapping[str, Any], variable: str, level: int) -> list[dict[str, object]]:
    nicas = section(config, "nicas")
    raw = nicas.get("dirac_points", [])
    if not isinstance(raw, list):
        raise ValueError("nicas.dirac_points deve ser uma lista.")
    points: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("Cada ponto NICAS deve ser um bloco YAML.")
        candidate = normalize_control(config, str(item.get("variable", variable)))
        if candidate != variable:
            continue
        points.append(
            {
                "longitude": float(item["longitude"]),
                "latitude": float(item["latitude"]),
                "level": level,
                "variable": variable,
            }
        )
    return points


def write_nicas_yaml(
    config: Mapping[str, Any], path: str | Path, variable: str, date: str, nvertlevels: int
) -> None:
    """Render one single-variable NICAS calibration input."""
    nicas = section(config, "nicas")
    level_from_top = int(nicas.get("dirac_level_from_top", 20))
    level = 1 if variable == "surface_pressure" else max(1, nvertlevels - level_from_top + 1)
    data = {
        "geometry": {
            "nml_file": "./namelist.atmosphere_240km",
            "streams_file": "./streams.atmosphere_240km",
            "deallocate non-da fields": True,
            "bump vunit": str(nicas.get("bump_vunit", "avgheight")),
        },
        "background": {
            "state variables": [variable],
            "filename": "./bg.nc",
            "date": date,
            "stream name": "control",
            "transform model to analysis": False,
        },
        "background error": {
            "covariance model": "SABER",
            "saber central block": {
                "saber block name": "BUMP_NICAS",
                "calibration": {
                    "io": {"files prefix": str(nicas.get("files_prefix", "mpas"))},
                    "drivers": dict(nicas.get("drivers", {})),
                    "nicas": dict(nicas.get("nicas", {})),
                    "dirac": _dirac_points(config, variable, level),
                    "input model files": [
                        {"parameter": "rh", "file": {"filename": "../mpas.cor_rh.nc", "date": date, "stream name": "control"}},
                        {"parameter": "rv", "file": {"filename": "../mpas.cor_rv.nc", "date": date, "stream name": "control"}},
                    ],
                    "output model files": [
                        {"parameter": "nicas_norm", "file": {"filename": "./mpas.nicas_norm.nc", "date": date, "stream name": "control"}},
                        {"parameter": "dirac_nicas", "file": {"filename": "./mpas.dirac_nicas.nc", "date": date, "stream name": "control"}},
                    ],
                },
            },
        },
    }
    write_text(Path(path), yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def write_nicas_pbs(config: Mapping[str, Any], run_dir: str | Path, variable: str) -> None:
    """Write a consistent PBS job for a per-variable NICAS calibration."""
    directory = Path(run_dir)
    ranks = int(config["mesh"].get("nproc", config.get("pbs", {}).get("nproc", 1)))
    spec = bmatrix_job_spec(
        config,
        name=f"NICAS_{variable}",
        run_dir=directory,
        command=mpi_command(config, ranks, str(toolbox_exe(config)), "./run_nicas.yaml", "./run_nicas.runlog"),
    )
    write_text(directory / "qsub_nicas.bash", render_pbs(spec))


def write_nicas_merge_files(config: Mapping[str, Any], workspace: str | Path) -> None:
    """Create deterministic NCO merge scripts and a scheduler wrapper."""
    root = Path(workspace)
    merge_dir = root / "merge"
    merge_dir.mkdir(parents=True, exist_ok=True)
    variables = control_file_names(config)
    ranks = int(config["mesh"].get("nproc", config.get("pbs", {}).get("nproc", 1)))
    padded = f"{ranks:06d}"

    for rank in range(1, ranks + 1):
        rank_padded = f"{rank:06d}"
        local_name = f"mpas_nicas_local_{padded}-{rank_padded}.nc"
        grids_name = f"mpas_nicas_grids_local_{padded}-{rank_padded}.nc"
        commands = ["#!/usr/bin/env bash", "set -euo pipefail", f"rm -f {local_name} {grids_name}"]
        for variable in variables:
            commands.extend(
                [
                    f"ncks -A ../{variable}/{local_name} {local_name}",
                    f"ncatted -O -a eulaVlliF_,global,d,, {local_name}",
                    f"ncks -A ../{variable}/{grids_name} {grids_name}",
                    f"ncatted -O -a eulaVlliF_,global,d,, {grids_name}",
                ]
            )
        write_text(merge_dir / f"merge_nicas_{rank_padded}.bash", "\n".join(commands) + "\n")

    global_commands = ["#!/usr/bin/env bash", "set -euo pipefail", "rm -f mpas_nicas.nc"]
    for variable in variables:
        global_commands.extend(
            [f"ncks -A ../{variable}/mpas_nicas.nc mpas_nicas.nc", "ncatted -O -a eulaVlliF_,global,d,, mpas_nicas.nc"]
        )
    write_text(merge_dir / "merge_nicas_global.bash", "\n".join(global_commands) + "\n")

    merge_runner = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "module load nco 2>/dev/null || true",
        "command -v ncks >/dev/null",
        "command -v ncatted >/dev/null",
        "rm -f stdout.log stderr.log merge.done mpas.nicas_norm.nc mpas.dirac_nicas.nc",
        "for script in merge_nicas_[0-9][0-9][0-9][0-9][0-9][0-9].bash; do chmod +x \"$script\"; ./\"$script\" & done",
        "wait",
        "chmod +x merge_nicas_global.bash",
        "./merge_nicas_global.bash",
    ]
    for variable in variables:
        merge_runner.extend(
            [
                f'ncks -A -v "{variable}" "../{variable}/mpas.nicas_norm.nc" mpas.nicas_norm.nc',
                f'ncks -A -v "{variable}" "../{variable}/mpas.dirac_nicas.nc" mpas.dirac_nicas.nc',
            ]
        )
    merge_runner.append("touch merge.done")
    write_text(merge_dir / "run_merge.sh", "\n".join(merge_runner) + "\n")

    spec = bmatrix_job_spec(
        config,
        name="NICASmerge",
        run_dir=merge_dir,
        command=("bash", "./run_merge.sh"),
    )
    # The merge runs local shell tasks; allocation remains explicit but no MPI launcher is used.
    spec = replace(spec, resources=replace(spec.resources, mpi_ranks=1))
    write_text(merge_dir / "qsub_nicas_merge.bash", render_pbs(spec))
