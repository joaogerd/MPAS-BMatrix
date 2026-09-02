"""Render VBAL inputs from the scientific contract and shared PBS renderer."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from ..scheduler import bmatrix_job_spec, render_pbs
from ..scientific_config import (
    bflow_sample_stem,
    normalize_control,
    ordered_control_file_names,
    section,
)
from ..shell import write_text
from .model import toolbox_exe


def _relation(config: Mapping[str, Any], relation: Mapping[str, Any]) -> dict[str, object]:
    balanced = relation.get("balanced_variable")
    unbalanced = relation.get("unbalanced_variable")
    if not isinstance(balanced, str) or not isinstance(unbalanced, str):
        raise ValueError("Cada relação VBAL requer balanced_variable e unbalanced_variable.")
    result: dict[str, object] = {
        "balanced variable": normalize_control(config, balanced),
        "unbalanced variable": normalize_control(config, unbalanced),
    }
    if "diagonal_regression" in relation:
        result["diagonal regression"] = bool(relation["diagonal_regression"])
    return result


def render_vbal_relations(config: Mapping[str, Any]) -> list[dict[str, object]]:
    """Render configured VBAL relation names into physical state variable names."""
    vbal = section(config, "vbal")
    raw_relations = vbal.get("relations", [])
    if not isinstance(raw_relations, list):
        raise ValueError("vbal.relations deve ser uma lista.")
    relations = [_relation(config, item) for item in raw_relations if isinstance(item, Mapping)]
    if len(relations) != len(raw_relations):
        raise ValueError("Cada item de vbal.relations deve ser um bloco YAML.")
    return relations


def write_vbal_yaml(config: Mapping[str, Any], path: str | Path, nmembers: int, date: str) -> None:
    """Render VBAL calibration without materializing transformed ensemble members."""
    vbal = section(config, "vbal")
    variables = list(ordered_control_file_names(config, vbal.get("group_variable_order")))
    stem = bflow_sample_stem(config)
    data: dict[str, object] = {
        "geometry": {"nml_file": "./namelist.atmosphere_240km", "streams_file": "./streams.atmosphere_240km"},
        "background": {
            "state variables": variables,
            "filename": "./bg.nc",
            "date": date,
            "stream name": "control",
            "transform model to analysis": False,
        },
        "background error": {
            "covariance model": "SABER",
            "iterative ensemble loading": False,
            "ensemble": {
                "members from template": {
                    "template": {
                        "state variables": variables,
                        "date": date,
                        "stream name": "control",
                        "transform model to analysis": False,
                        "filename": f"../samples/{stem}_%mem%.nc",
                    },
                    "pattern": "%mem%",
                    "nmembers": nmembers,
                    "zero padding": 3,
                }
            },
            "saber central block": {"saber block name": "ID"},
            "saber outer blocks": [
                {
                    "saber block name": "BUMP_VerticalBalance",
                    "calibration": {
                        "io": {"files prefix": str(vbal.get("files_prefix", "mpas"))},
                        "drivers": {
                            str(key).replace("_", " "): value
                            for key, value in dict(vbal.get("drivers", {})).items()
                        },
                        "sampling": dict(vbal.get("sampling", {})),
                        "diagnostics": {"target ensemble size": nmembers},
                        "vertical balance": {
                            "vbal": render_vbal_relations(config),
                            "pseudo inverse": bool(vbal.get("pseudo_inverse", True)),
                            "dominant mode": int(vbal.get("dominant_mode", 20)),
                        },
                    },
                }
            ],
        },
    }
    write_text(Path(path), yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def write_vbal_pbs(config: Mapping[str, Any], run_dir: str | Path) -> None:
    """Write the standard PBS script for one VBAL calibration job."""
    directory = Path(run_dir)
    ranks = int(config["mesh"].get("nproc", config.get("pbs", {}).get("nproc", 1)))
    spec = bmatrix_job_spec(
        config,
        name="mpasjediBTrainingVBAL",
        run_dir=directory,
        command=("mpiexec", "-n", str(ranks), str(toolbox_exe(config)), "./run_vbal.yaml", "./run_vbal.runlog"),
    )
    write_text(directory / "qsub_vbal.bash", render_pbs(spec))
