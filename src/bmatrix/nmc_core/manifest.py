"""Read the minimal producer/consumer contract used by BFLOW."""
from __future__ import annotations

import csv
from pathlib import Path

from .model import NMCManifestPair, normalize_time


class ManifestError(ValueError):
    """The tab-separated NMC producer manifest is invalid."""


def _pair_columns(fieldnames: list[str] | None, path: Path) -> tuple[str, str]:
    """Resolve legacy or current mpaswf state columns for one producer manifest."""
    if not fieldnames or "valid_time" not in fieldnames:
        raise ManifestError(
            f"NMC manifest {path} must contain a tab-separated valid_time column."
        )

    fields = set(fieldnames)
    if {"f048", "f024"}.issubset(fields):
        return "f048", "f024"
    if {"f048_state", "f024_state"}.issubset(fields):
        return "f048_state", "f024_state"

    raise ManifestError(
        f"NMC manifest {path} must contain either tab-separated columns "
        "valid_time, f048, f024 or valid_time, f048_state, f024_state."
    )


def read_manifest(path: str | Path) -> list[NMCManifestPair]:
    """Read producer rows and normalize current/legacy forecast state columns.

    The legacy BFLOW producer schema uses ``f048``/``f024``.  Current mpaswf
    manifests expose the same MPAS-JEDI da_state products explicitly as
    ``f048_state``/``f024_state`` and additionally carry restart paths.  BFLOW
    consumes the state products; restart columns are intentionally ignored.
    """
    path = Path(path)
    if not path.is_file():
        raise ManifestError(f"NMC manifest does not exist: {path}")
    pairs: list[NMCManifestPair] = []
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        f048_column, f024_column = _pair_columns(reader.fieldnames, path)
        for index, row in enumerate(reader, start=2):
            raw_valid = (row.get("valid_time") or "").strip()
            raw_f048 = (row.get(f048_column) or "").strip()
            raw_f024 = (row.get(f024_column) or "").strip()
            if not raw_f048 or not raw_f024:
                raise ManifestError(
                    f"NMC manifest {path}:{index} has an empty {f048_column} or {f024_column} path."
                )
            try:
                valid_time = normalize_time(raw_valid)
            except ValueError as error:
                raise ManifestError(f"Invalid valid_time at {path}:{index}: {error}") from error
            pairs.append(NMCManifestPair(valid_time, Path(raw_f048), Path(raw_f024)))
    if not pairs:
        raise ManifestError(f"NMC manifest has no pair rows: {path}")
    return pairs
