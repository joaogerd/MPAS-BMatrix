#!/usr/bin/env python3
"""Compare Single Observation analysis increments between A/B workspaces.

This is a diagnostic, not an acceptance gate. It verifies that the two SO
backgrounds are numerically identical and reports how different the analysis
increments ``analysis - background`` are for every common numeric field.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare SO A/B analysis increments.")
    parser.add_argument("reference", type=Path, help="materialized SO workspace")
    parser.add_argument("candidate", type=Path, help="in-memory SO workspace")
    parser.add_argument("--top", type=int, default=20, help="maximum rows to print")
    return parser


def _analysis(root: Path) -> Path:
    matches = sorted(root.glob("an.*.nc"))
    if len(matches) != 1:
        raise RuntimeError(f"Esperado exatamente um an.*.nc em {root}; encontrados {len(matches)}")
    return matches[0]


def _as_float(variable) -> np.ndarray | None:
    dtype = np.dtype(variable.dtype)
    if dtype.kind not in "biuf":
        return None
    values = variable[:]
    if np.ma.isMaskedArray(values):
        values = np.ma.asarray(values, dtype=np.float64).filled(np.nan)
    return np.asarray(values, dtype=np.float64)


def _rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(values * values))) if values.size else 0.0


def _ratio(numerator: float, denominator: float) -> float:
    if denominator > 0.0:
        return numerator / denominator
    return 0.0 if numerator == 0.0 else math.inf


def main() -> int:
    args = _parser().parse_args()
    reference = args.reference.resolve()
    candidate = args.candidate.resolve()
    ref_bg_path = reference / "bg_so.nc"
    cand_bg_path = candidate / "bg_so.nc"
    ref_an_path = _analysis(reference)
    cand_an_path = _analysis(candidate)

    try:
        import netCDF4
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("netCDF4 é necessário para executar esta comparação") from exc

    for path in (ref_bg_path, cand_bg_path, ref_an_path, cand_an_path):
        if not path.is_file():
            raise SystemExit(f"ERRO: arquivo obrigatório ausente: {path}")

    rows: list[dict[str, object]] = []
    background_problems: list[str] = []
    with (
        netCDF4.Dataset(ref_bg_path) as ref_bg,
        netCDF4.Dataset(cand_bg_path) as cand_bg,
        netCDF4.Dataset(ref_an_path) as ref_an,
        netCDF4.Dataset(cand_an_path) as cand_an,
    ):
        common = sorted(
            set(ref_bg.variables)
            & set(cand_bg.variables)
            & set(ref_an.variables)
            & set(cand_an.variables)
        )
        for name in common:
            ref_bg_values = _as_float(ref_bg.variables[name])
            cand_bg_values = _as_float(cand_bg.variables[name])
            ref_an_values = _as_float(ref_an.variables[name])
            cand_an_values = _as_float(cand_an.variables[name])
            if any(value is None for value in (ref_bg_values, cand_bg_values, ref_an_values, cand_an_values)):
                continue
            assert ref_bg_values is not None
            assert cand_bg_values is not None
            assert ref_an_values is not None
            assert cand_an_values is not None
            shapes = {ref_bg_values.shape, cand_bg_values.shape, ref_an_values.shape, cand_an_values.shape}
            if len(shapes) != 1:
                continue

            ref_bg_nan = np.isnan(ref_bg_values)
            cand_bg_nan = np.isnan(cand_bg_values)
            if np.any(ref_bg_nan != cand_bg_nan):
                background_problems.append(f"{name}: padrão NaN diferente no background")
                continue
            finite_bg = np.isfinite(ref_bg_values) & np.isfinite(cand_bg_values)
            background_delta = cand_bg_values[finite_bg] - ref_bg_values[finite_bg]
            background_max_delta = float(np.max(np.abs(background_delta))) if background_delta.size else 0.0
            if background_max_delta != 0.0:
                background_problems.append(
                    f"{name}: backgrounds A/B não são idênticos; max_abs={background_max_delta:.17g}"
                )

            finite = (
                np.isfinite(ref_bg_values)
                & np.isfinite(cand_bg_values)
                & np.isfinite(ref_an_values)
                & np.isfinite(cand_an_values)
            )
            if not np.any(finite):
                continue
            bg = ref_bg_values[finite]
            ref_increment = ref_an_values[finite] - bg
            cand_increment = cand_an_values[finite] - bg
            delta_increment = cand_increment - ref_increment

            ref_inc_rms = _rms(ref_increment)
            cand_inc_rms = _rms(cand_increment)
            delta_rms = _rms(delta_increment)
            ref_inc_max = float(np.max(np.abs(ref_increment)))
            cand_inc_max = float(np.max(np.abs(cand_increment)))
            delta_max = float(np.max(np.abs(delta_increment)))
            rows.append(
                {
                    "variable": name,
                    "dtype": str(np.dtype(ref_an.variables[name].dtype)),
                    "n": int(np.count_nonzero(finite)),
                    "ref_inc_rms": ref_inc_rms,
                    "cand_inc_rms": cand_inc_rms,
                    "delta_rms": delta_rms,
                    "relative_l2": _ratio(delta_rms, ref_inc_rms),
                    "ref_inc_max": ref_inc_max,
                    "cand_inc_max": cand_inc_max,
                    "delta_max": delta_max,
                    "relative_max": _ratio(delta_max, ref_inc_max),
                    "background_max_delta": background_max_delta,
                }
            )

    print("=== SO increment A/B diagnostic ===")
    print(f"REFERENCE={reference}")
    print(f"CANDIDATE={candidate}")
    if background_problems:
        for problem in background_problems:
            print(f"BACKGROUND_ERROR {problem}")
        return 1
    print("BACKGROUND_STATUS=IDENTICAL")

    if not rows:
        print("ERRO: nenhum campo numérico comum entre background e análise.")
        return 1

    ranked = sorted(rows, key=lambda row: float(row["relative_l2"]), reverse=True)
    for row in ranked[: max(1, args.top)]:
        print(
            "INCREMENT "
            f"variable={row['variable']} dtype={row['dtype']} n={row['n']} "
            f"ref_rms={float(row['ref_inc_rms']):.17g} "
            f"cand_rms={float(row['cand_inc_rms']):.17g} "
            f"delta_rms={float(row['delta_rms']):.17g} "
            f"relative_l2={float(row['relative_l2']):.17g} "
            f"ref_max={float(row['ref_inc_max']):.17g} "
            f"cand_max={float(row['cand_inc_max']):.17g} "
            f"delta_max={float(row['delta_max']):.17g} "
            f"relative_max={float(row['relative_max']):.17g}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
