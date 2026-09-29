"""Completeness checks for NMC manifests consumed by BFLOW."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping
import hashlib
import json

import netCDF4

from .manifest import ManifestError, read_manifest
from .model import MINIMUM_PAIRS, NMCManifestPair, parse_time


def _require_product(path: Path, label: str) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size == 0:
        raise ManifestError(f"Required {label} product is missing or empty: {path}")
    return {"path": str(path.resolve()), "bytes": path.stat().st_size}


def validate_pairs(pairs: list[NMCManifestPair], *, minimum_pairs: int = MINIMUM_PAIRS) -> dict[str, object]:
    """Validate chronology, uniqueness and product availability for NMC inputs."""
    if minimum_pairs < MINIMUM_PAIRS:
        raise ManifestError(
            f"minimum_pairs cannot be below {MINIMUM_PAIRS}; fewer samples are only suitable for isolated code tests."
        )
    if len(pairs) < minimum_pairs:
        raise ManifestError(
            f"NMC manifest contains {len(pairs)} pair(s), but B-matrix calibration requires at least {minimum_pairs}."
        )

    previous = None
    seen: set[str] = set()
    records = []
    for pair in pairs:
        parsed = parse_time(pair.valid_time)
        if pair.valid_time in seen:
            raise ManifestError(f"Duplicate NMC valid_time: {pair.valid_time}")
        if previous is not None and parsed <= previous:
            raise ManifestError("NMC manifest valid_time values must be strictly increasing.")
        if pair.f048.resolve() == pair.f024.resolve():
            raise ManifestError(f"f048 and f024 resolve to the same file for {pair.valid_time}.")
        records.append(
            {
                "valid_time": pair.valid_time,
                "f048": _require_product(pair.f048, f"f048 for {pair.valid_time}"),
                "f024": _require_product(pair.f024, f"f024 for {pair.valid_time}"),
            }
        )
        seen.add(pair.valid_time)
        previous = parsed
    return {"valid": True, "minimum_pairs": minimum_pairs, "pairs": records}


def _validate_contract_sidecar(path: Path, pair_count: int) -> dict[str, object] | None:
    """Validate the optional versioned mpaswf producer contract."""
    sidecar = path.with_suffix(".json")
    if not sidecar.is_file():
        return None
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"Invalid NMC contract sidecar {sidecar}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ManifestError(f"NMC contract sidecar must contain a JSON object: {sidecar}")
    expected = {
        "schema_version": 1,
        "contract": "monan-nmc-forecast-pairs-v1",
        "producer": "mpaswf",
        "consumer": "MPAS-BMatrix",
        "manifest": path.name,
        "manifest_format": "tsv",
        "columns": ["valid_time", "f048_state", "f024_state", "f048_restart", "f024_restart"],
        "pair_count": pair_count,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ManifestError(
                f"NMC contract sidecar {sidecar} has {key}={payload.get(key)!r}; expected {value!r}."
            )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if payload.get("manifest_sha256") != digest:
        raise ManifestError(
            f"NMC contract sidecar SHA-256 does not match manifest {path}; regenerate the mpaswf manifest."
        )
    return {
        "path": str(sidecar.resolve()),
        "contract": payload["contract"],
        "schema_version": payload["schema_version"],
        "producer": payload["producer"],
        "verified_sha256": digest,
    }



def _required_bflow_input_variables(config: Mapping[str, object]) -> tuple[str, ...]:
    """Derive the MPAS input-variable contract from the scientific BFLOW YAML."""
    bflow = config.get("bflow")
    if not isinstance(bflow, Mapping):
        raise ManifestError("Resolved configuration has no bflow mapping.")
    names: set[str] = set()
    transform = bflow.get("wind_transform")
    if isinstance(transform, Mapping):
        for key in ("zonal_file_variable", "meridional_file_variable", "template_file_variable"):
            value = transform.get(key)
            if isinstance(value, str) and value:
                names.add(value)
    copied = bflow.get("copy_variables", [])
    if isinstance(copied, list):
        names.update(value for value in copied if isinstance(value, str) and value)
    derived = bflow.get("derived_variables", [])
    if isinstance(derived, list):
        for spec in derived:
            if not isinstance(spec, Mapping):
                continue
            for key in ("theta_file", "mixing_ratio_file", "template_file"):
                value = spec.get(key)
                if isinstance(value, str) and value:
                    names.add(value)
            inputs = spec.get("inputs")
            if isinstance(inputs, list):
                names.update(value for value in inputs if isinstance(value, str) and value)
    return tuple(sorted(names))


def _decode_xtime(variable: object) -> tuple[str, ...]:
    """Decode MPAS character xtime values without assuming one fixed string width."""
    import numpy as np
    values = np.asarray(variable[:])
    if values.ndim > 1 and values.dtype.kind in {"S", "U"}:
        decoded: list[str] = []
        for row in values:
            parts = [
                item.decode() if isinstance(item, (bytes, np.bytes_)) else str(item)
                for item in np.asarray(row).reshape(-1)
            ]
            decoded.append("".join(parts).rstrip("\x00 "))
        return tuple(decoded)
    return tuple(
        str(item.decode() if isinstance(item, (bytes, np.bytes_)) else item).rstrip("\x00 ")
        for item in values.reshape(-1)
    )


def _inspect_state(path: Path, required: tuple[str, ...], expected_time: str) -> dict[str, object]:
    """Validate one MPAS da_state before expensive BFLOW preprocessing."""
    try:
        with netCDF4.Dataset(path) as dataset:
            missing = [name for name in required if name not in dataset.variables]
            if missing:
                raise ManifestError(f"BFLOW input {path} is missing required MPAS variables: {', '.join(missing)}")
            for dim in ("Time", "nCells", "nVertLevels"):
                if dim not in dataset.dimensions:
                    raise ManifestError(f"BFLOW input {path} is missing required MPAS dimension {dim}.")
            if "xtime" not in dataset.variables:
                raise ManifestError(f"BFLOW input {path} is missing MPAS time variable xtime.")
            times = _decode_xtime(dataset.variables["xtime"])
            if expected_time not in times:
                raise ManifestError(
                    f"BFLOW input {path} xtime={times!r} does not contain manifest valid_time {expected_time!r}."
                )
            return {
                "data_model": dataset.data_model,
                "nCells": len(dataset.dimensions["nCells"]),
                "nVertLevels": len(dataset.dimensions["nVertLevels"]),
                "required_variables": list(required),
                "xtime": list(times),
            }
    except OSError as exc:
        raise ManifestError(f"Cannot open BFLOW NetCDF input {path}: {exc}") from exc


def validate_scientific_pairs(
    pairs: list[NMCManifestPair], config: Mapping[str, object]
) -> dict[str, object]:
    """Validate NetCDF structure, valid time and pairwise mesh compatibility."""
    required = _required_bflow_input_variables(config)
    records: list[dict[str, object]] = []
    reference_shape: tuple[int, int] | None = None
    for pair in pairs:
        expected = pair.valid_time
        f048 = _inspect_state(pair.f048, required, expected)
        f024 = _inspect_state(pair.f024, required, expected)
        shape48 = (int(f048["nCells"]), int(f048["nVertLevels"]))
        shape24 = (int(f024["nCells"]), int(f024["nVertLevels"]))
        if shape48 != shape24:
            raise ManifestError(
                f"NMC pair {pair.valid_time} uses incompatible MPAS grids: f048={shape48}, f024={shape24}."
            )
        if reference_shape is None:
            reference_shape = shape48
        elif shape48 != reference_shape:
            raise ManifestError(
                f"NMC campaign changes MPAS grid at {pair.valid_time}: {shape48}; expected {reference_shape}."
            )
        records.append({"valid_time": pair.valid_time, "f048": f048, "f024": f024})
    return {
        "valid": True,
        "required_variables": list(required),
        "mesh_shape": list(reference_shape) if reference_shape else None,
        "pairs": records,
    }


def validate_manifest(
    path: str | Path,
    *,
    minimum_pairs: int = MINIMUM_PAIRS,
    config: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Read and validate a producer manifest and its optional versioned contract."""
    path = Path(path)
    pairs = read_manifest(path)
    report = validate_pairs(pairs, minimum_pairs=minimum_pairs)
    report["manifest"] = str(path.resolve())
    report["pair_count"] = len(pairs)
    contract = _validate_contract_sidecar(path, len(pairs))
    report["producer_contract"] = contract
    report["producer_contract_verified"] = contract is not None
    if config is not None:
        report["scientific_contract"] = validate_scientific_pairs(pairs, config)
        report["scientific_contract_verified"] = True
    else:
        report["scientific_contract"] = None
        report["scientific_contract_verified"] = False
    return report
