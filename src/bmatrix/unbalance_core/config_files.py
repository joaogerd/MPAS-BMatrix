"""Render UNBALANCE inputs from the scientific contract."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from ..scheduler import bmatrix_job_spec, render_pbs
from ..scientific_config import bflow_sample_stem, ordered_control_file_names, section
from ..shell import write_text
from ..vbal_core.config_files import render_vbal_relations
from .model import unbalance_exe


def _read_drivers(unbalance: Mapping[str, Any]) -> dict[str, object]:
    """Return validated BUMP read flags for the explicit UNBALANCE stage."""
    configured = unbalance.get("drivers", {})
    if not isinstance(configured, Mapping):
        raise ValueError("unbalance.drivers deve ser um bloco YAML.")
    defaults: dict[str, object] = {
        "read local sampling": True,
        "read global sampling": False,
        "read vertical balance": True,
    }
    return {**defaults, **{str(key): value for key, value in configured.items()}}


def write_unbalance_yaml(config: Mapping[str, Any], path: str | Path, nmembers: int, date: str) -> None:
    """Render the YAML consumed by ``mpasjedi_unbalance_ensemble.x``."""
    vbal = section(config, "vbal")
    unbalance = config.get("unbalance", {})
    if not isinstance(unbalance, Mapping):
        raise ValueError("unbalance deve ser um bloco YAML.")
    variables = list(ordered_control_file_names(config, vbal.get("group_variable_order")))
    stem = bflow_sample_stem(config)
    data: dict[str, object] = {
        "geometry": {
            "nml_file": "./namelist.atmosphere_240km",
            "streams_file": "./streams.atmosphere_240km",
        },
        "background": {
            "state variables": variables,
            "filename": "./bg.nc",
            "date": date,
            "stream name": "control",
            "transform model to analysis": False,
        },
        "input variables": variables,
        "ensemble": {
            "members from template": {
                "template": {
                    "filename": f"../samples/{stem}_%mem%.nc",
                    "state variables": variables,
                    "date": date,
                    "stream name": "control",
                    "transform model to analysis": False,
                },
                "pattern": "%mem%",
                "nmembers": nmembers,
                "zero padding": 3,
            }
        },
        "inverse blocks": [
            {
                "saber block name": "BUMP_VerticalBalance",
                "read": {
                    "io": {"files prefix": str(vbal.get("files_prefix", "mpas"))},
                    "drivers": _read_drivers(unbalance),
                    "vertical balance": {
                        "vbal": render_vbal_relations(config),
                        "pseudo inverse": bool(vbal.get("pseudo_inverse", True)),
                        "dominant mode": int(vbal.get("dominant_mode", 20)),
                    },
                },
            }
        ],
        "output": {
            "filename": f"../samplesUnbalanced/{stem}_%{{member}}%.nc",
            "date": date,
            "stream name": "control",
        },
    }
    write_text(Path(path), yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def write_unbalance_pbs(config: Mapping[str, Any], run_dir: str | Path) -> None:
    """Write the PBS script for applying K2^-1 to the ensemble."""
    directory = Path(run_dir)
    ranks = int(config["mesh"].get("nproc", config.get("pbs", {}).get("nproc", 1)))
    exe = unbalance_exe(config)
    spec = bmatrix_job_spec(
        config,
        name="mpasjediUnbalanceEns",
        run_dir=directory,
        command=(
            "mpiexec",
            "-n",
            str(ranks),
            str(exe),
            "./run_unbalance.yaml",
            "./run_unbalance.runlog",
        ),
    )
    write_text(directory / "qsub_unbalance.bash", render_pbs(spec))
