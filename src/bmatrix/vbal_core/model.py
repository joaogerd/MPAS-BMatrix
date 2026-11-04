from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

from ..scientific_config import bflow_product
from ..shell import require_file


TIME_FORMAT = "%Y-%m-%d_%H:%M:%S"


@dataclass(frozen=True)
class Sample:
    """One BFLOW sample consumed by the VBAL calibration stage."""

    valid_time: str
    ptb: Path
    full_f24: Path
    template_fields: Path


def compact_time(value: str) -> str:
    """Return a YYYYMMDDHH representation of a configured valid time."""
    return datetime.strptime(value, TIME_FORMAT).strftime("%Y%m%d%H")


def iso_date(value: str) -> str:
    """Return an ISO-8601 instant understood by JEDI YAML inputs."""
    return datetime.strptime(value, TIME_FORMAT).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_bflow_samples(config: Mapping[str, object], bflow_workspace: str | Path) -> list[Sample]:
    """Read completed BFLOW samples using declared product filenames.

    The input manifest remains the producer/consumer contract; output filenames
    are obtained from ``bflow.products`` rather than being embedded in code.
    """
    workspace = Path(bflow_workspace)
    manifest = require_file(workspace / "manifest.tsv", "BFLOW manifest.tsv")
    perturbation = bflow_product(config, "perturbation")
    newer_full = bflow_product(config, "newer_full")
    samples: list[Sample] = []
    with manifest.open(newline="") as file:
        reader = csv.DictReader(file, delimiter="\t")
        for row in reader:
            valid_time = str(row["valid_time"])
            output = workspace / "output" / compact_time(valid_time)
            ptb = require_file(output / perturbation, f"perturbação para {valid_time}")
            full_f24 = require_file(output / newer_full, f"forecast processado para {valid_time}")
            template_fields = require_file(row["f024"], f"f024 completo para {valid_time}")
            samples.append(Sample(valid_time, ptb, full_f24, template_fields))
    if not samples:
        raise RuntimeError("Nenhuma amostra BFLOW encontrada.")
    return samples


def covariance_root(config: Mapping[str, object]) -> Path:
    """Return the root directory for calibrated covariance products."""
    project = config.get("project")
    if not isinstance(project, Mapping):
        raise ValueError("project deve ser um bloco YAML.")
    return Path(str(project["work_root"])) / "bmatrix" / "covariance"


def vbal_workspace(config: Mapping[str, object], bflow_workspace: str | Path) -> Path:
    """Resolve the deterministic VBAL workspace for one BFLOW run."""
    return covariance_root(config) / "vbal" / Path(bflow_workspace).name


def toolbox_exe(config: Mapping[str, object]) -> Path:
    """Resolve the configured JEDI/SABER covariance toolbox executable."""
    install = config.get("install")
    if not isinstance(install, Mapping):
        raise ValueError("install deve ser um bloco YAML.")
    path = Path(str(install["root"])) / "bin" / "mpasjedi_error_covariance_toolbox.x"
    return require_file(path, "mpasjedi_error_covariance_toolbox.x")


def vbal_date(vbal_root: str | Path) -> str:
    """Read the calibration date from a rendered VBAL YAML file."""
    text = require_file(Path(vbal_root) / "VBAL" / "run_vbal.yaml", "run_vbal.yaml").read_text()
    match = re.search(r"(?m)^\s*date:\s*(?:&date\s*)?['\"]?([^'\"\n ]+)", text)
    if not match:
        raise RuntimeError("Data principal não encontrada no run_vbal.yaml")
    return match.group(1)
