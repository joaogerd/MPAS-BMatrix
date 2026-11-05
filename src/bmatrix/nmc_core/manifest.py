"""Read the minimal producer/consumer contract used by BFLOW."""
from __future__ import annotations

import csv
from pathlib import Path

from .model import NMCManifestPair, normalize_time


class ManifestError(ValueError):
    """The tab-separated NMC producer manifest is invalid."""


def _pair_columns(fieldnames: list[str] | None, path: Path) -> tuple[str, str, bool]:
    """Identify the supported producer manifest schema by exact column names."""
    if not fieldnames or "valid_time" not in fieldnames:
        raise ManifestError(f"O manifesto NMC não contém a coluna valid_time: {path}")
    fields = set(fieldnames)
    if {"older_state", "newer_state", "older_lead_hours", "newer_lead_hours"}.issubset(fields):
        return "older_state", "newer_state", True
    if {"older_state", "newer_state"} & fields:
        raise ManifestError(
            f"Manifesto NMC v2 incompleto: {path}. "
            "Declare older_state, newer_state, older_lead_hours e newer_lead_hours."
        )
    if {"f048", "f024"}.issubset(fields):
        return "f048", "f024", False
    if {"f048_state", "f024_state"}.issubset(fields):
        return "f048_state", "f024_state", False
    raise ManifestError(
        f"Manifesto NMC sem colunas de previsões reconhecidas: {path}. "
        "Use f048_state/f024_state (v1) ou older_state/newer_state "
        "com older_lead_hours/newer_lead_hours (v2)."
    )


def read_manifest(path: str | Path) -> list[NMCManifestPair]:
    """Read legacy 24/48-hour or versioned arbitrary-lead MPAS forecast pairs."""
    path = Path(path)
    if not path.is_file():
        raise ManifestError(f"NMC manifest does not exist: {path}")
    pairs: list[NMCManifestPair] = []
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        older_column, newer_column, v2 = _pair_columns(reader.fieldnames, path)
        for index, row in enumerate(reader, start=2):
            raw_valid = (row.get("valid_time") or "").strip()
            raw_older = (row.get(older_column) or "").strip()
            raw_newer = (row.get(newer_column) or "").strip()
            if not raw_older or not raw_newer:
                raise ManifestError(
                    f"Manifesto NMC {path}:{index} possui caminho vazio em "
                    f"{older_column} ou {newer_column}."
                )
            try:
                valid_time = normalize_time(raw_valid)
            except ValueError as error:
                raise ManifestError(
                    f"Horário de validade inválido em {path}:{index}: {error}"
                ) from error
            if v2:
                try:
                    older = int(row.get("older_lead_hours") or "")
                    newer = int(row.get("newer_lead_hours") or "")
                except ValueError as error:
                    raise ManifestError(
                        f"Leads inválidos na linha {index} do manifesto NMC: "
                        "informe horas inteiras positivas."
                    ) from error
                if newer <= 0 or older <= newer:
                    raise ManifestError(
                        f"Leads inconsistentes em {path}:{index}: "
                        f"older={older}, newer={newer}. "
                        "O forecast mais antigo precisa ter lead maior."
                    )
            else:
                older, newer = 48, 24
            def resolve_product(raw: str) -> Path:
                candidate = Path(raw).expanduser()
                return candidate if candidate.is_absolute() else path.parent / candidate
            pairs.append(NMCManifestPair(
                valid_time, resolve_product(raw_older), resolve_product(raw_newer),
                older_lead_hours=older, newer_lead_hours=newer,
            ))
    if not pairs:
        raise ManifestError(f"NMC manifest has no pair rows: {path}")
    return pairs
