"""Render the complete-B DIRAC toolbox configuration from YAML settings."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from ..scheduler import bmatrix_job_spec, render_pbs
from ..scientific_config import (
    control_aliases,
    control_code_names,
    normalize_control_code,
    require_background_covers_analysis,
    section,
)
from ..shell import write_text
from ..so_core.config_files import nicas_read_grids, render_vbal_code_relations, vbal_read_aliases
from ..vbal_core.model import toolbox_exe


def _number_list(value: object, name: str) -> list[float]:
    """Validate a nonempty numeric YAML sequence."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise ValueError(f"{name} deve ser uma lista numérica não vazia.")
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} deve conter apenas números.") from exc


def _configured_points(raw: Mapping[str, Any]) -> tuple[list[float], list[float]]:
    """Read paired DIRAC points or the legacy parallel latitude/longitude lists."""
    points = raw.get("points")
    if points is not None:
        if not isinstance(points, Sequence) or isinstance(points, (str, bytes)) or not points:
            raise ValueError("dirac.points deve ser uma lista não vazia.")
        latitudes: list[float] = []
        longitudes: list[float] = []
        for item in points:
            if not isinstance(item, Mapping):
                raise ValueError("Cada item de dirac.points deve ser um bloco YAML.")
            try:
                latitudes.append(float(item["latitude"]))
                longitudes.append(float(item["longitude"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    "Cada item de dirac.points requer latitude e longitude numéricas."
                ) from exc
        return latitudes, longitudes

    latitudes = _number_list(raw.get("latitudes"), "dirac.latitudes")
    longitudes = _number_list(raw.get("longitudes"), "dirac.longitudes")
    if len(latitudes) != len(longitudes):
        raise ValueError("dirac.latitudes e dirac.longitudes devem ter o mesmo tamanho.")
    return latitudes, longitudes


def _settings(config: Mapping[str, Any], analysis_variables: list[str]) -> dict[str, object]:
    """Return validated, explicit DIRAC settings from the scientific contract."""
    raw = section(config, "dirac")
    latitudes, longitudes = _configured_points(raw)
    index = int(raw.get("index", 1))
    if not 1 <= index <= len(latitudes):
        raise ValueError("dirac.index deve selecionar um ponto configurado.")
    ndir = int(raw.get("ndir", 1))
    if ndir < 1:
        raise ValueError("dirac.ndir deve ser positivo.")
    variable = raw.get("variable")
    if not isinstance(variable, str):
        raise ValueError("dirac.variable deve ser uma variável de controle declarada.")
    background_variables = require_background_covers_analysis(
        raw.get("background_variables", []),
        analysis_variables,
        "dirac",
    )
    return {
        "ndir": ndir,
        "ildir": index,
        "variable": normalize_control_code(config, variable),
        "dirLats": latitudes,
        "dirLons": longitudes,
        "background_variables": list(background_variables),
    }


def write_dirac_yaml(
    config: Mapping[str, Any],
    path: str | Path,
    date: str,
    nicas_dir: Path,
    stddev_file: Path,
    vbal_dir: Path,
) -> None:
    """Render a full-B DIRAC test for the covariance toolbox.

    The file applies the same BUMP_NICAS, StdDev, BUMP_VerticalBalance and
    Control2Analysis composition used by the SO test. The ``dirac`` block follows
    the covariance toolbox contract used by the validated main branch: complete
    point lists plus singular ``ildir``/``dirvar`` selectors.
    """
    controls = list(control_code_names(config))
    nicas = section(config, "nicas")
    vbal = section(config, "vbal")
    single = section(config, "single_observation")
    analysis_variables = list(single.get("analysis_variables", []))
    settings = _settings(config, analysis_variables)
    aliases = control_aliases(config)
    data: dict[str, object] = {
        "geometry": {
            "nml_file": "./namelist.atmosphere_240km",
            "streams_file": "./streams.atmosphere_240km",
            "deallocate non-da fields": True,
            "alias": aliases,
        },
        "background": {
            "state variables": settings["background_variables"],
            "filename": "./bg.nc",
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
                        "files prefix": str(nicas.get("files_prefix", "mpas")),
                        "alias": aliases,
                    },
                    "drivers": {
                        "multivariate strategy": str(
                            nicas.get("drivers", {}).get(
                                "multivariate strategy",
                                "univariate",
                            )
                        ),
                        "read local nicas": True,
                    },
                    "grids": nicas_read_grids(config),
                },
            },
            "saber outer blocks": [
                {
                    "saber block name": "StdDev",
                    "read": {
                        "model file": {
                            "filename": str(stddev_file),
                            "date": date,
                            "stream name": "control",
                        }
                    },
                },
                {
                    "saber block name": "BUMP_VerticalBalance",
                    "read": {
                        "io": {
                            "data directory": str(vbal_dir),
                            "files prefix": str(vbal.get("files_prefix", "mpas")),
                            "alias": vbal_read_aliases(config),
                        },
                        "drivers": {
                            "read local sampling": True,
                            "read vertical balance": True,
                        },
                        "model": {"nearest 3d level": "bottom"},
                        "vertical balance": {
                            "vbal": render_vbal_code_relations(config)
                        },
                    },
                },
            ],
            "linear variable change": {
                "linear variable change name": "Control2Analysis",
                "input variables": controls,
                "output variables": analysis_variables,
            },
        },
        "dirac": {
            "ndir": settings["ndir"],
            "dirLats": settings["dirLats"],
            "dirLons": settings["dirLons"],
            "ildir": settings["ildir"],
            "dirvar": settings["variable"],
        },
        "output dirac": {
            "filename": "./mpas.dirac.nc",
            "date": date,
            "stream name": "control",
        },
    }
    write_text(Path(path), yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def write_dirac_pbs(config: Mapping[str, Any], run_dir: str | Path) -> None:
    """Write the standard PBS script for the full-B DIRAC toolbox diagnostic."""
    directory = Path(run_dir)
    ranks = int(config["mesh"].get("nproc", config.get("pbs", {}).get("nproc", 1)))
    spec = bmatrix_job_spec(
        config,
        name="DiracTest",
        run_dir=directory,
        command=(
            "mpiexec",
            "-n",
            str(ranks),
            str(toolbox_exe(config)),
            "./run_dirac.yaml",
            "./run_dirac.runlog",
        ),
    )
    write_text(directory / "qsub_dirac.bash", render_pbs(spec))
