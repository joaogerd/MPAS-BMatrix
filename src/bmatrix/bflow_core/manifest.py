"""Read and write the BFLOW input contract."""
from __future__ import annotations

import csv
from pathlib import Path

from ..nmc_core.manifest import read_manifest as read_nmc_manifest
from .model import BflowPair


def read_manifest(path: str | Path) -> list[BflowPair]:
    """Read producer manifests, accepting ISO-8601 or MPAS valid-time values."""
    return [
        BflowPair(
            pair.valid_time, pair.older, pair.newer,
            older_lead_hours=pair.older_lead_hours,
            newer_lead_hours=pair.newer_lead_hours,
        )
        for pair in read_nmc_manifest(path)
    ]


def write_manifest(path: str | Path, pairs: list[BflowPair]) -> Path:
    """Persist the input pair including lead durations for non-legacy NMC cases."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy = all((pair.older_lead_hours, pair.newer_lead_hours) == (48, 24)
                 for pair in pairs)
    columns = (["valid_time", "f048", "f024"] if legacy else [
        "valid_time", "older_lead_hours", "newer_lead_hours",
        "older_state", "newer_state",
    ])
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        for pair in pairs:
            if legacy:
                writer.writerow({
                    "valid_time": pair.valid_time,
                    "f048": str(pair.older), "f024": str(pair.newer),
                })
            else:
                writer.writerow({
                    "valid_time": pair.valid_time,
                    "older_lead_hours": pair.older_lead_hours,
                    "newer_lead_hours": pair.newer_lead_hours,
                    "older_state": str(pair.older),
                    "newer_state": str(pair.newer),
                })
    return path
