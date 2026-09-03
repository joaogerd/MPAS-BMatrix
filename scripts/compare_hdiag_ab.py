#!/usr/bin/env python3
"""Compare materialized and in-memory HDIAG NetCDF products."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

PRODUCTS = ("mpas.stddev.nc", "mpas.cor_rh.nc", "mpas.cor_rv.nc")


@dataclass(frozen=True)
class Result:
    product: str
    variable: str
    dtype: str
    shape: str
    n_values: int
    fail_count: int
    fail_fraction: float
    ref_abs_max: float
    cand_abs_max: float
    max_abs: float
    rms: float
    max_rel: float
    max_scaled_error: float
    worst_ref: float
    worst_candidate: float
    worst_abs_delta: float
    finite_mismatch: int
    nan_mismatch: int
    inf_mismatch: int
    status: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare legacy materialized and in-memory HDIAG products."
    )
    parser.add_argument(
        "reference",
        type=Path,
        help="HDIAG directory from the legacy materialized path",
    )
    parser.add_argument(
        "candidate",
        type=Path,
        help="HDIAG directory from the in-memory VBAL path",
    )
    parser.add_argument(
        "--rtol",
        type=float,
        default=1.0e-6,
        help="relative tolerance for element-wise comparison (default: 1e-6)",
    )
    parser.add_argument(
        "--atol",
        type=float,
        default=1.0e-8,
        help="absolute tolerance for element-wise comparison (default: 1e-8)",
    )
    parser.add_argument("--output", type=Path, help="optional CSV output path")
    return parser


def _resolve_product(root: Path, name: str) -> Path:
    direct = root / name
    nested = root / "HDIAG" / name
    if direct.is_file():
        return direct
    if nested.is_file():
        return nested
    raise FileNotFoundError(f"produto ausente sob {root}: {name}")


def _iter_variables(group, prefix: str = "") -> Iterable[tuple[str, object]]:
    for name, variable in group.variables.items():
        path = f"{prefix}/{name}" if prefix else name
        yield path, variable
    for name, child in group.groups.items():
        path = f"{prefix}/{name}" if prefix else name
        yield from _iter_variables(child, path)


def _variable_map(dataset) -> dict[str, object]:
    return dict(_iter_variables(dataset))


def _as_float_array(variable) -> np.ndarray | None:
    dtype = np.dtype(variable.dtype)
    if dtype.kind not in "biuf":
        return None
    values = variable[:]
    if np.ma.isMaskedArray(values):
        values = np.ma.asarray(values, dtype=np.float64).filled(np.nan)
    return np.asarray(values, dtype=np.float64)


def _dtype_label(reference, candidate) -> str:
    ref_dtype = str(np.dtype(reference.dtype))
    cand_dtype = str(np.dtype(candidate.dtype))
    return ref_dtype if ref_dtype == cand_dtype else f"{ref_dtype} != {cand_dtype}"


def _shape_mismatch(product: str, name: str, reference, candidate, ref_shape, cand_shape) -> Result:
    return Result(
        product=product,
        variable=name,
        dtype=_dtype_label(reference, candidate),
        shape=f"{ref_shape} != {cand_shape}",
        n_values=int(np.prod(ref_shape, dtype=np.int64)) if ref_shape else 1,
        fail_count=0,
        fail_fraction=0.0,
        ref_abs_max=math.inf,
        cand_abs_max=math.inf,
        max_abs=math.inf,
        rms=math.inf,
        max_rel=math.inf,
        max_scaled_error=math.inf,
        worst_ref=math.nan,
        worst_candidate=math.nan,
        worst_abs_delta=math.inf,
        finite_mismatch=0,
        nan_mismatch=0,
        inf_mismatch=0,
        status="SHAPE_MISMATCH",
    )


def _scaled_error(abs_delta: np.ndarray, tolerance: np.ndarray) -> np.ndarray:
    scaled = np.empty_like(abs_delta, dtype=np.float64)
    positive = tolerance > 0.0
    scaled[positive] = abs_delta[positive] / tolerance[positive]
    zero_tolerance = ~positive
    scaled[zero_tolerance] = np.where(abs_delta[zero_tolerance] == 0.0, 0.0, np.inf)
    return scaled


def _compare_variable(
    product: str,
    name: str,
    reference,
    candidate,
    *,
    rtol: float,
    atol: float,
) -> Result | None:
    ref = _as_float_array(reference)
    cand = _as_float_array(candidate)
    if ref is None or cand is None:
        return None
    if ref.shape != cand.shape:
        return _shape_mismatch(product, name, reference, candidate, ref.shape, cand.shape)

    ref_nan = np.isnan(ref)
    cand_nan = np.isnan(cand)
    nan_mismatch = int(np.count_nonzero(ref_nan != cand_nan))

    ref_inf = np.isinf(ref)
    cand_inf = np.isinf(cand)
    inf_mismatch = int(np.count_nonzero(ref_inf != cand_inf))

    ref_finite = np.isfinite(ref)
    cand_finite = np.isfinite(cand)
    finite_mismatch = int(np.count_nonzero(ref_finite != cand_finite))
    both = ref_finite & cand_finite
    n_values = int(ref.size)

    if np.any(both):
        ref_values = ref[both]
        cand_values = cand[both]
        delta = cand_values - ref_values
        abs_delta = np.abs(delta)
        max_abs = float(np.max(abs_delta))
        rms = float(np.sqrt(np.mean(delta * delta)))
        ref_abs_max = float(np.max(np.abs(ref_values)))
        cand_abs_max = float(np.max(np.abs(cand_values)))

        rel_mask = np.abs(ref_values) > atol
        if np.any(rel_mask):
            max_rel = float(np.max(abs_delta[rel_mask] / np.abs(ref_values[rel_mask])))
        else:
            max_rel = 0.0

        tolerance = atol + rtol * np.abs(ref_values)
        fail_mask = abs_delta > tolerance
        fail_count = int(np.count_nonzero(fail_mask))
        fail_fraction = fail_count / n_values if n_values else 0.0
        scaled = _scaled_error(abs_delta, tolerance)
        worst_index = int(np.argmax(scaled))
        max_scaled_error = float(scaled[worst_index])
        worst_ref = float(ref_values[worst_index])
        worst_candidate = float(cand_values[worst_index])
        worst_abs_delta = float(abs_delta[worst_index])
        close = fail_count == 0
    else:
        ref_abs_max = 0.0
        cand_abs_max = 0.0
        max_abs = 0.0
        rms = 0.0
        max_rel = 0.0
        max_scaled_error = 0.0
        worst_ref = math.nan
        worst_candidate = math.nan
        worst_abs_delta = 0.0
        fail_count = 0
        fail_fraction = 0.0
        close = True

    status = "PASS"
    if not close or finite_mismatch or nan_mismatch or inf_mismatch:
        status = "FAIL"

    return Result(
        product=product,
        variable=name,
        dtype=_dtype_label(reference, candidate),
        shape=str(ref.shape),
        n_values=n_values,
        fail_count=fail_count,
        fail_fraction=fail_fraction,
        ref_abs_max=ref_abs_max,
        cand_abs_max=cand_abs_max,
        max_abs=max_abs,
        rms=rms,
        max_rel=max_rel,
        max_scaled_error=max_scaled_error,
        worst_ref=worst_ref,
        worst_candidate=worst_candidate,
        worst_abs_delta=worst_abs_delta,
        finite_mismatch=finite_mismatch,
        nan_mismatch=nan_mismatch,
        inf_mismatch=inf_mismatch,
        status=status,
    )


def compare_product(
    reference: Path,
    candidate: Path,
    *,
    rtol: float,
    atol: float,
) -> tuple[list[Result], list[str]]:
    try:
        import netCDF4
    except ImportError as exc:  # pragma: no cover - runtime environment check
        raise SystemExit("netCDF4 é necessário para executar esta comparação") from exc

    problems: list[str] = []
    rows: list[Result] = []
    with netCDF4.Dataset(reference) as ref_ds, netCDF4.Dataset(candidate) as cand_ds:
        ref_vars = _variable_map(ref_ds)
        cand_vars = _variable_map(cand_ds)
        ref_names = set(ref_vars)
        cand_names = set(cand_vars)
        for missing in sorted(ref_names - cand_names):
            problems.append(
                f"{reference.name}: variável ausente no candidato: {missing}"
            )
        for extra in sorted(cand_names - ref_names):
            problems.append(f"{reference.name}: variável extra no candidato: {extra}")
        for name in sorted(ref_names & cand_names):
            row = _compare_variable(
                reference.name,
                name,
                ref_vars[name],
                cand_vars[name],
                rtol=rtol,
                atol=atol,
            )
            if row is not None:
                rows.append(row)
    return rows, problems


def _write(rows: list[Result], stream) -> None:
    writer = csv.writer(stream)
    writer.writerow(
        [
            "product",
            "variable",
            "dtype",
            "shape",
            "n_values",
            "fail_count",
            "fail_fraction",
            "ref_abs_max",
            "cand_abs_max",
            "max_abs",
            "rms",
            "max_rel",
            "max_scaled_error",
            "worst_ref",
            "worst_candidate",
            "worst_abs_delta",
            "finite_mismatch",
            "nan_mismatch",
            "inf_mismatch",
            "status",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.product,
                row.variable,
                row.dtype,
                row.shape,
                row.n_values,
                row.fail_count,
                f"{row.fail_fraction:.17g}",
                f"{row.ref_abs_max:.17g}",
                f"{row.cand_abs_max:.17g}",
                f"{row.max_abs:.17g}",
                f"{row.rms:.17g}",
                f"{row.max_rel:.17g}",
                f"{row.max_scaled_error:.17g}",
                f"{row.worst_ref:.17g}",
                f"{row.worst_candidate:.17g}",
                f"{row.worst_abs_delta:.17g}",
                row.finite_mismatch,
                row.nan_mismatch,
                row.inf_mismatch,
                row.status,
            ]
        )


def main() -> int:
    args = _parser().parse_args()
    rows: list[Result] = []
    problems: list[str] = []

    for product in PRODUCTS:
        try:
            reference = _resolve_product(args.reference, product)
            candidate = _resolve_product(args.candidate, product)
        except FileNotFoundError as exc:
            problems.append(str(exc))
            continue
        product_rows, product_problems = compare_product(
            reference,
            candidate,
            rtol=args.rtol,
            atol=args.atol,
        )
        rows.extend(product_rows)
        problems.extend(product_problems)

    _write(rows, sys.stdout)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", newline="") as stream:
            _write(rows, stream)

    for problem in problems:
        print(f"ERROR: {problem}", file=sys.stderr)

    failed = any(row.status != "PASS" for row in rows)
    if problems or failed or not rows:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
