"""Domain values and deterministic paths for BFLOW NMC preprocessing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import re
from typing import Iterator, Mapping

from ..errors import ConfigurationError
from ..mpas_core.model import bflow_file

TIME_FORMAT = "%Y-%m-%d_%H:%M:%S"


@dataclass(frozen=True, slots=True)
class BflowPair:
    """One pair of equal-valid-time f048/f024 MPAS outputs."""

    valid_time: str
    f048: Path
    f024: Path


def parse_time(value: str) -> datetime:
    """Parse an MPAS timestamp in ``YYYY-MM-DD_HH:MM:SS`` form."""
    return datetime.strptime(value, TIME_FORMAT)


def format_time(value: datetime) -> str:
    """Format one datetime in canonical MPAS timestamp form."""
    return value.strftime(TIME_FORMAT)


def compact_time(value: str) -> str:
    """Return ``YYYYMMDDHH`` for workspace product directories."""
    return parse_time(value).strftime("%Y%m%d%H")


def iter_valid_times(start: str, end: str, step_hours: int) -> Iterator[str]:
    """Yield inclusive valid times at a strictly positive interval."""
    if step_hours <= 0:
        raise ConfigurationError("valid_interval_hours deve ser positivo.")
    current = parse_time(start)
    last = parse_time(end)
    if current > last:
        raise ConfigurationError("start_valid_time deve ser anterior ou igual a end_valid_time.")
    step = timedelta(hours=step_hours)
    while current <= last:
        yield format_time(current)
        current += step


def bflow_settings(config: Mapping[str, object]) -> Mapping[str, object]:
    """Return and validate the BFLOW scientific configuration block."""
    bflow = config.get("bflow")
    if not isinstance(bflow, Mapping):
        raise ConfigurationError("bflow deve ser um bloco YAML.")
    return bflow


def product_name(config: Mapping[str, object], key: str) -> str:
    """Return one configured BFLOW filename."""
    products = bflow_settings(config).get("products")
    if not isinstance(products, Mapping):
        raise ConfigurationError("bflow.products deve ser um bloco YAML.")
    name = products.get(key)
    if not isinstance(name, str) or not name.strip():
        raise ConfigurationError(f"bflow.products.{key} deve ser um nome de arquivo não vazio.")
    return name


def nmc_leads(config: Mapping[str, object]) -> tuple[int, int]:
    """Return configured older/newer NMC lead hours as ``(f48, f24)``."""
    nmc = bflow_settings(config).get("nmc")
    if not isinstance(nmc, Mapping):
        raise ConfigurationError("bflow.nmc deve ser um bloco YAML.")
    try:
        older = int(nmc["older_lead_hours"])
        newer = int(nmc["newer_lead_hours"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigurationError("bflow.nmc deve definir older_lead_hours e newer_lead_hours.") from exc
    if older <= newer or newer <= 0:
        raise ConfigurationError("bflow.nmc requer older_lead_hours > newer_lead_hours > 0.")
    return older, newer


def default_workspace(config: Mapping[str, object], start_valid_time: str, end_valid_time: str) -> Path:
    """Build the deterministic BFLOW workspace path for a time range."""
    mesh = config.get("mesh")
    project = config.get("project")
    if not isinstance(mesh, Mapping) or not isinstance(project, Mapping):
        raise ConfigurationError("mesh e project devem ser blocos YAML.")
    try:
        nproc = int(mesh["nproc"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigurationError("Declare mesh.nproc as a positive integer in the case YAML.") from exc
    if nproc < 1:
        raise ConfigurationError("mesh.nproc must be positive.")
    # Include the mesh (or an explicit case id) so different experiments with
    # the same MPI count and time window cannot silently reuse one workspace.
    case_id = project.get("case_id") or mesh.get("name")
    if not isinstance(case_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", case_id):
        raise ConfigurationError(
            "Set mesh.name or project.case_id to a non-empty filename-safe case identifier."
        )
    return (
        Path(str(project["work_root"]))
        / "bmatrix"
        / "bflow_preprocessing"
        / f"np{nproc}_{compact_time(start_valid_time)}_{compact_time(end_valid_time)}_case-{case_id}"
    )


def build_pairs_from_range(
    config: Mapping[str, object],
    start_valid_time: str,
    end_valid_time: str,
    step_hours: int,
    dt: int,
) -> list[BflowPair]:
    """Resolve source MPAS files for all configured NMC valid times."""
    older_lead, newer_lead = nmc_leads(config)
    pairs: list[BflowPair] = []
    for valid_time in iter_valid_times(start_valid_time, end_valid_time, step_hours):
        valid = parse_time(valid_time)
        old_init = format_time(valid - timedelta(hours=older_lead))
        new_init = format_time(valid - timedelta(hours=newer_lead))
        pairs.append(
            BflowPair(
                valid_time=valid_time,
                f048=bflow_file(config, old_init, older_lead, dt),
                f024=bflow_file(config, new_init, newer_lead, dt),
            )
        )
    return pairs
