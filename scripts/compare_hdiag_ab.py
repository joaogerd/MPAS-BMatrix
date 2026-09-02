#!/usr/bin/env python3
"""Compare materialized and in-memory HDIAG NetCDF products.

The tool is intended for the VBAL/HDIAG migration validation. It compares the
three standard HDIAG products recursively, including variables stored in NetCDF
groups, and reports numerical differences without requiring byte identity.
"""
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
    shape: str
    max_abs: float
    rms: float
    max_rel: float
    finite_mismatch: int
    nan_mismatch: int
    inf_mismatch: int
    status: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare legacy materialized and in-memory HDIAG products."
    )
    parser.add_argument("reference", type=Path, help="HDIAG directory from the legacy materialized path")
    parser.add_argument("candidate", type=Path, help="HDIAG directory from the in-memory VBAL path")
    parser.add_argument("--rtol", type=float, default=1.0e-6, help="relative tolerance for np.allclose (default: 1e-6)")
    parser.add_argument("--atol", type=float, default=1.0e-8, help="absolute tolerance for np.allclose (default: 1e-8)")
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
    if dtype.kind not in "biufc":
        return None
    values = variable[:]
    if np.ma.isMaskedArray(values):
        values = np.ma.filled(values, np.nan)
    return np.asarray(values, dtype=np.float64)


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
        return Result(product, name, f"{ref.shape} != {cand.shape}", math.inf, math.inf, math.inf, 0, 0, 0, "SHAPE_MISMATCH")

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

    if np.any(both):
        delta = cand[both] - ref[both]
        max_abs = float(np.max(np.abs(delta)))
        rms = float(np.sqrt(np.mean(delta * delta)))
        rel_mask = np.abs(ref[both]) > atol
        if np.any(rel_mask):
            max_rel = float(np.max(np.abs(delta[rel_mask]) / np.abs(ref[both][rel_mask])))
        else:
            max_rel = 0.0
        close = bool(np.allclose(cand[both], ref[both], rtol=rtol, atol=atol, equal_nan=True))
    else:
        max_abs = 0.0
        rms = 0.0
        max_rel = 0.0
        close = True

    status = "PASS" if close and not (finite_mismatch or nan_mismatch or inf_mismatch) else "FAIL"
    return Result(
        product,
        name,
        str(ref.shape),
        max_abs,
        rms,
        max_rel,
        finite_mismatch,
        nan_mismatch,
        inf_mismatch,
        status,
    )


def compare_product(reference: Path, candidate: Path, *, rtol: float, atol: float) -> tuple[list[Result], list[str]]:
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
            problems.append(f"{reference.name}: variável ausente no candidato: {missing}")
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
            "shape",
            "max_abs",
            "rms",
            "max_rel",
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
                row.shape,
                f"{row.max_abs:.17g}",
                f"{row.rms:.17g}",
                f"{row.max_rel:.17g}",
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
