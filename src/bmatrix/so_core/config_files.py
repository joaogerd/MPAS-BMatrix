"""Render the Single Observation validation from the scientific contract."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

import yaml

from ..scheduler import bmatrix_job_spec, mpi_command, render_pbs
from ..scientific_config import (
    control_aliases,
    control_code_names,
    control_read_grids,
    normalize_control_code,
    require_background_covers_analysis,
    section,
    vbal_composite_aliases,
)
from ..shell import write_text
from .model import so_artifacts, variational_exe


def _observers(config: Mapping[str, Any], variant: str, epoch: str) -> list[dict[str, object]]:
    single = section(config, "single_observation")
    variants = single.get("variants", {})
    observations = single.get("observations", {})
    if not isinstance(variants, Mapping) or not isinstance(observations, Mapping):
        raise ValueError("single_observation.variants/observations devem ser blocos YAML.")
    names = variants.get(variant)
    if not isinstance(names, list) or not all(isinstance(item, str) for item in names):
        raise ValueError(f"Variante SO inválida ou não configurada: {variant}")
    result: list[dict[str, object]] = []
    for key in names:
        raw = observations.get(key)
        if not isinstance(raw, Mapping):
            raise ValueError(f"Observação SO ausente: {key}")
        result.append(
            {
                "obs space": {
                    "name": str(raw["name"]),
                    "simulated variables": [str(raw["simulated_variable"])],
                    "obsdatain": {
                        "engine": {
                            "type": "GenList",
                            "lats": [float(raw["latitude"])],
                            "lons": [float(raw["longitude"])],
                            "vert coord type": "pressure",
                            "vert coords": [float(raw["pressure"])],
                            "dateTimes": [0],
                            "epoch": f"seconds since {epoch}",
                            "obs errors": [float(raw["error"])],
                            "obs values": [float(raw["value"])],
                        }
                    },
                    "obsdataout": {"engine": {"type": "H5File", "obsfile": f"./{raw['output_file']}"}},
                },
                "obs operator": {
                    "name": "VertInterp",
                    "vertical coordinate": "air_pressure",
                    "interpolation method": "log-linear",
                },
            }
        )
    return result


def nicas_read_grids(config: Mapping[str, Any]) -> list[dict[str, dict[str, list[str]]]]:
    """Split NICAS read grids by vertical dimension."""
    return control_read_grids(config)


def vbal_read_aliases(config: Mapping[str, Any]) -> list[dict[str, str]]:
    """Return simple and pair-group aliases needed to read VBAL products."""
    vbal = section(config, "vbal")
    return control_aliases(config) + vbal_composite_aliases(config, vbal.get("group_variable_order"))


def render_vbal_code_relations(config: Mapping[str, Any]) -> list[dict[str, object]]:
    """Render VBAL relations in canonical JEDI control names for B application."""
    vbal = section(config, "vbal")
    raw_relations = vbal.get("relations", [])
    if not isinstance(raw_relations, list):
        raise ValueError("vbal.relations deve ser uma lista.")
    relations: list[dict[str, object]] = []
    for raw in raw_relations:
        if not isinstance(raw, Mapping):
            raise ValueError("Cada item de vbal.relations deve ser um bloco YAML.")
        balanced = raw.get("balanced_variable")
        unbalanced = raw.get("unbalanced_variable")
        if not isinstance(balanced, str) or not isinstance(unbalanced, str):
            raise ValueError("Cada relação VBAL requer balanced_variable e unbalanced_variable.")
        relation: dict[str, object] = {
            "balanced variable": normalize_control_code(config, balanced),
            "unbalanced variable": normalize_control_code(config, unbalanced),
        }
        if "diagonal_regression" in raw:
            relation["diagonal regression"] = bool(raw["diagonal_regression"])
        relations.append(relation)
    return relations


def write_so_yaml(
    config: Mapping[str, Any],
    path: str | Path,
    date: str,
    nicas_dir: Path,
    stddev_file: Path,
    vbal_dir: Path,
    variant: str = "default",
) -> None:
    """Render the variational SO test using a calibrated B matrix."""
    so_artifacts(variant)
    single = section(config, "single_observation")
    analysis_date = datetime.strptime(date, "%Y-%m-%dT%H:%M:%SZ")
    before = int(single.get("window_hours_before_analysis", 3))
    window_hours = int(single.get("window_hours", 6))
    window_begin = (analysis_date - timedelta(hours=before)).strftime("%Y-%m-%dT%H:%M:%SZ")
    controls = list(control_code_names(config))
    analysis_variables = list(single.get("analysis_variables", []))
    background_variables = require_background_covers_analysis(
        single.get("background_variables", []),
        analysis_variables,
        "single_observation",
    )
    relations = render_vbal_code_relations(config)
    aliases = control_aliases(config)
    data = {
        "output": {"filename": "./an.$Y-$M-$D_$h.$m.$s.nc", "stream name": "analysis"},
        "variational": {
            "minimizer": {"algorithm": str(single.get("minimizer", "DRPCG"))},
            "iterations": [
                {
                    "geometry": {"nml_file": "./namelist.atmosphere_240km", "streams_file": "./streams.atmosphere_240km"},
                    "gradient norm reduction": float(single.get("gradient_norm_reduction", 1e-3)),
                    "diagnostics": {"departures": "ombg"},
                    "ninner": int(single.get("ninner", 10)),
                }
            ],
        },
        "final": {"diagnostics": {"departures": "oman"}},
        "cost function": {
            "cost type": "3D-Var",
            "time window": {"begin": window_begin, "length": f"PT{window_hours}H"},
            "jb evaluation": False,
            "geometry": {
                "nml_file": "./namelist.atmosphere_240km",
                "streams_file": "./streams.atmosphere_240km",
                "deallocate non-da fields": True,
                "alias": aliases,
            },
            "analysis variables": analysis_variables,
            "background": {
                "state variables": background_variables,
                "filename": "./bg_so.nc",
                "date": date,
                "transform model to analysis": False,
            },
            "background error": {
                "covariance model": "SABER",
                "saber central block": {
                    "saber block name": "BUMP_NICAS",
                    "active variables": controls,
                    "read": {
                        "io": {
                            "data directory": str(nicas_dir),
                            "files prefix": str(section(config, "nicas").get("files_prefix", "mpas")),
                            "alias": aliases,
                        },
                        "drivers": {"multivariate strategy": str(section(config, "nicas").get("drivers", {}).get("multivariate strategy", "univariate")), "read local nicas": True},
                        "grids": nicas_read_grids(config),
                    },
                },
                "saber outer blocks": [
                    {"saber block name": "StdDev", "read": {"model file": {"filename": str(stddev_file), "date": date, "stream name": "control"}}},
                    {
                        "saber block name": "BUMP_VerticalBalance",
                        "read": {
                            "io": {
                                "data directory": str(vbal_dir),
                                "files prefix": str(section(config, "vbal").get("files_prefix", "mpas")),
                                "alias": vbal_read_aliases(config),
                            },
                            "drivers": {"read local sampling": True, "read vertical balance": True},
                            "model": {"nearest 3d level": "bottom"},
                            "vertical balance": {"vbal": relations},
                        },
                    },
                ],
                "linear variable change": {
                    "linear variable change name": "Control2Analysis",
                    "input variables": controls,
                    "output variables": analysis_variables,
                },
            },
            "observations": {"observers": _observers(config, variant, date)},
        },
    }
    write_text(Path(path), yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def write_so_pbs(config: Mapping[str, Any], run_dir: str | Path, variant: str = "default") -> None:
    """Write the standard PBS job for a selected SO variant."""
    directory = Path(run_dir)
    artifacts = so_artifacts(variant)
    ranks = int(config["mesh"].get("nproc", config.get("pbs", {}).get("nproc", 1)))
    spec = bmatrix_job_spec(
        config,
        name=f"SO_{variant}",
        run_dir=directory,
        command=mpi_command(config, ranks, str(variational_exe(config)), f"./{artifacts['yaml']}", f"./{artifacts['runlog']}"),
        stdout=artifacts["stdout"],
        stderr=artifacts["stderr"],
    )
    write_text(directory / artifacts["pbs"], render_pbs(spec))


def write_so_t_only_diagnostic_pbs(config: Mapping[str, Any], run_dir: Path) -> None:
    """Create a lightweight marker for the intentionally optional t-only debug run."""
    write_text(run_dir / "qsub_so_t_only_debug.bash", "#!/usr/bin/env bash\necho 'SO t-only debug placeholder'\n")
