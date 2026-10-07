"""Completeness checks for NMC manifests consumed by BFLOW."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping
import hashlib
import json

import numpy as np

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


def _mesh_contract(config: Mapping[str, object]) -> tuple[str, Path, int]:
    """Return the declared mesh identity and canonical MPAS grid file."""
    mesh = config.get("mesh")
    if not isinstance(mesh, Mapping):
        raise ManifestError("Resolved configuration has no mesh mapping.")
    name = mesh.get("name")
    grid = mesh.get("grid")
    if not isinstance(name, str) or not name:
        raise ManifestError("mesh.name is required for NMC scientific preflight.")
    if not isinstance(grid, str) or not grid:
        raise ManifestError("mesh.grid is required for NMC scientific preflight.")
    nvertlevels = mesh.get("nvertlevels")
    if not isinstance(nvertlevels, int) or isinstance(nvertlevels, bool) or nvertlevels <= 0:
        raise ManifestError("mesh.nvertlevels must be an explicit positive integer.")
    path = Path(grid).expanduser()
    if not path.is_file():
        raise ManifestError(f"Canonical MPAS mesh.grid does not exist: {path}")
    return name, path, nvertlevels


def _mesh_geometry(path: Path) -> dict[str, object]:
    """Read the minimal geometry needed to identify an MPAS cell mesh."""
    try:
        with netCDF4.Dataset(path) as dataset:
            for name in ("latCell", "lonCell"):
                if name not in dataset.variables:
                    raise ManifestError(f"MPAS mesh identity source {path} is missing {name}.")
            lat = np.asarray(dataset.variables["latCell"][:], dtype=np.float64).reshape(-1)
            lon = np.asarray(dataset.variables["lonCell"][:], dtype=np.float64).reshape(-1)
    except OSError as exc:
        raise ManifestError(f"Cannot open MPAS mesh identity source {path}: {exc}") from exc
    if lat.shape != lon.shape or lat.size == 0:
        raise ManifestError(f"Invalid latCell/lonCell geometry in {path}.")
    digest = hashlib.sha256()
    digest.update(np.asarray(lat, dtype="<f8").tobytes(order="C"))
    digest.update(np.asarray(lon, dtype="<f8").tobytes(order="C"))
    return {"lat": lat, "lon": lon, "sha256": digest.hexdigest(), "nCells": int(lat.size)}


def _validate_mesh_identity(
    state_path: Path,
    dataset: object,
    *,
    mesh_name: str,
    canonical: Mapping[str, object],
) -> dict[str, object]:
    """Check compatibility, reporting whether state geometry is directly proven.

    The pinned MPAS immutable da_state stream does not publish cell coordinates.
    Such states can establish cell-count compatibility with the configured case,
    but cannot independently prove geometry or cell ordering. Never present the
    canonical grid fingerprint as a fingerprint measured from those states.
    """
    n_cells = len(dataset.dimensions["nCells"])
    if n_cells != canonical["nCells"]:
        raise ManifestError(
            f"BFLOW input {state_path} does not match canonical mesh {mesh_name}: "
            f"nCells={n_cells}; expected {canonical['nCells']}."
        )
    identity = {
        "name": mesh_name,
        "geometry_sha256": canonical["sha256"],
        "nCells": n_cells,
    }
    present = [name for name in ("latCell", "lonCell") if name in dataset.variables]
    if not present:
        return {
            **identity,
            "state_proof": "case-grid-plus-cell-count",
            "state_geometry_verified": False,
        }
    if len(present) != 2:
        raise ManifestError(
            f"BFLOW input {state_path} has incomplete horizontal coordinates: "
            "latCell and lonCell must both be present or both absent."
        )
    lat = np.asarray(dataset.variables["latCell"][:], dtype=np.float64).reshape(-1)
    lon = np.asarray(dataset.variables["lonCell"][:], dtype=np.float64).reshape(-1)
    ref_lat = canonical["lat"]
    ref_lon = canonical["lon"]
    if lat.shape != ref_lat.shape or lon.shape != ref_lon.shape:
        raise ManifestError(
            f"BFLOW input {state_path} does not match canonical mesh {mesh_name}: coordinate shape differs."
        )
    # MPAS state and grid files should carry the same cell coordinates. allclose
    # tolerates representation precision without accepting a geometrically
    # different mesh.
    if not np.allclose(lat, ref_lat, rtol=0.0, atol=1.0e-12) or not np.allclose(
        lon, ref_lon, rtol=0.0, atol=1.0e-12
    ):
        raise ManifestError(
            f"BFLOW input {state_path} does not match canonical MPAS mesh {mesh_name} latCell/lonCell."
        )
    return {
        **identity,
        "state_proof": "state-coordinates-match-case-grid",
        "state_geometry_verified": True,
    }


def _vertical_grid_contract(config: Mapping[str, object], expected_nvertlevels: int) -> dict[str, object]:
    """Fingerprint the case's canonical MPAS vertical interfaces from static.invariant."""
    static = config.get("static")
    if not isinstance(static, Mapping) or not isinstance(static.get("invariant"), str):
        raise ManifestError("static.invariant is required to identify the MPAS vertical grid.")
    path = Path(str(static["invariant"])).expanduser()
    if not path.is_file():
        raise ManifestError(f"Canonical static.invariant does not exist: {path}")
    try:
        with netCDF4.Dataset(path) as dataset:
            if "zgrid" not in dataset.variables:
                raise ManifestError(
                    f"Canonical static.invariant {path} is missing MPAS vertical-grid variable zgrid."
                )
            values = np.asarray(dataset.variables["zgrid"][:], dtype=np.float64)
            dims = tuple(dataset.variables["zgrid"].dimensions)
    except OSError as exc:
        raise ManifestError(f"Cannot open canonical static.invariant {path}: {exc}") from exc
    if "nVertLevelsP1" not in dims or "nCells" not in dims:
        raise ManifestError(
            f"static.invariant zgrid has dimensions {dims!r}; expected nVertLevelsP1 and nCells."
        )
    level_axis = dims.index("nVertLevelsP1")
    if values.shape[level_axis] != expected_nvertlevels + 1:
        raise ManifestError(
            f"static.invariant zgrid has {values.shape[level_axis]} interfaces, but "
            f"mesh.nvertlevels={expected_nvertlevels} requires {expected_nvertlevels + 1}."
        )
    digest = hashlib.sha256(np.asarray(values, dtype="<f8").tobytes(order="C")).hexdigest()
    return {
        "source": str(path.resolve()),
        "variable": "zgrid",
        "dimensions": list(dims),
        "interface_count": int(values.shape[level_axis]),
        "sha256": digest,
        "values": values,
    }


def _inspect_state(path: Path, required: tuple[str, ...], expected_time: str, *, mesh_name: str, canonical_mesh: Mapping[str, object], vertical_grid: Mapping[str, object]) -> dict[str, object]:
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
            mesh_identity = _validate_mesh_identity(
                path, dataset, mesh_name=mesh_name, canonical=canonical_mesh
            )
            vertical_proof = "case-invariant-plus-level-count"
            if "zgrid" in dataset.variables:
                state_zgrid = np.asarray(dataset.variables["zgrid"][:], dtype=np.float64)
                reference_zgrid = vertical_grid["values"]
                if state_zgrid.shape != reference_zgrid.shape or not np.allclose(
                    state_zgrid, reference_zgrid, rtol=0.0, atol=1.0e-8
                ):
                    raise ManifestError(
                        f"BFLOW input {path} zgrid does not match the canonical static.invariant vertical grid."
                    )
                vertical_proof = "state-zgrid-matches-case-invariant"
            return {
                "data_model": dataset.data_model,
                "nCells": len(dataset.dimensions["nCells"]),
                "nVertLevels": len(dataset.dimensions["nVertLevels"]),
                "required_variables": list(required),
                "xtime": list(times),
                "mesh": mesh_identity,
                "vertical_grid_proof": vertical_proof,
            }
    except OSError as exc:
        raise ManifestError(f"Cannot open BFLOW NetCDF input {path}: {exc}") from exc


def validate_scientific_pairs(
    pairs: list[NMCManifestPair], config: Mapping[str, object]
) -> dict[str, object]:
    """Validate NetCDF structure, valid time and pairwise mesh compatibility."""
    required = _required_bflow_input_variables(config)
    mesh_name, mesh_path, expected_nvertlevels = _mesh_contract(config)
    canonical_mesh = _mesh_geometry(mesh_path)
    vertical_grid = _vertical_grid_contract(config, expected_nvertlevels)
    records: list[dict[str, object]] = []
    reference_shape: tuple[int, int] | None = None
    for pair in pairs:
        expected = pair.valid_time
        f048 = _inspect_state(
            pair.f048, required, expected, mesh_name=mesh_name, canonical_mesh=canonical_mesh, vertical_grid=vertical_grid
        )
        f024 = _inspect_state(
            pair.f024, required, expected, mesh_name=mesh_name, canonical_mesh=canonical_mesh, vertical_grid=vertical_grid
        )
        shape48 = (int(f048["nCells"]), int(f048["nVertLevels"]))
        shape24 = (int(f024["nCells"]), int(f024["nVertLevels"]))
        for label, shape in (("f048", shape48), ("f024", shape24)):
            if shape[1] != expected_nvertlevels:
                raise ManifestError(
                    f"NMC {label} state at {pair.valid_time} has nVertLevels={shape[1]}, "
                    f"but this case declares mesh.nvertlevels={expected_nvertlevels}."
                )
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
        "mesh_identity": {
            "name": mesh_name,
            "grid": str(mesh_path.resolve()),
            "geometry_sha256": canonical_mesh["sha256"],
            "nCells": canonical_mesh["nCells"],
            "nVertLevels": expected_nvertlevels,
            "state_geometry_verified": all(
                record[lead]["mesh"]["state_geometry_verified"]
                for record in records for lead in ("f048", "f024")
            ),
            "vertical_identity": {
                "source": vertical_grid["source"],
                "variable": vertical_grid["variable"],
                "dimensions": vertical_grid["dimensions"],
                "interface_count": vertical_grid["interface_count"],
                "zgrid_sha256": vertical_grid["sha256"],
                "state_proof": (
                    "direct-when-zgrid-present; otherwise case-invariant-plus-level-count"
                ),
            },
        },
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
