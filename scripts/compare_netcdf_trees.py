#!/usr/bin/env python3
"""Compare selected NetCDF products under two validation workspaces."""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from compare_hdiag_ab import Result, _write, compare_product


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare matching NetCDF products under two directory trees.")
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument(
        "--include",
        action="append",
        required=True,
        help="relative glob to compare; repeat for multiple product families",
    )
    parser.add_argument("--rtol", type=float, default=1.0e-6)
    parser.add_argument("--atol", type=float, default=1.0e-8)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print every numeric comparison row; the complete CSV is written regardless",
    )
    return parser


def _matches(root: Path, patterns: list[str]) -> dict[str, Path]:
    matches: dict[str, Path] = {}
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file():
                matches[str(path.relative_to(root))] = path
    return matches


def _print_summary(rows: list[Result], common_files: int, problems: list[str]) -> None:
    passed = sum(row.status == "PASS" for row in rows)
    failed = len(rows) - passed
    if rows:
        worst = max(rows, key=lambda row: row.max_rel)
        max_abs_row = max(rows, key=lambda row: row.max_abs)
        finite_mismatch = sum(row.finite_mismatch for row in rows)
        nan_mismatch = sum(row.nan_mismatch for row in rows)
        inf_mismatch = sum(row.inf_mismatch for row in rows)
        print(
            "SUMMARY "
            f"files={common_files} numeric_variables={len(rows)} passed={passed} failed={failed} "
            f"problems={len(problems)} max_rel={worst.max_rel:.17g} "
            f"worst_rel={worst.product}:{worst.variable} "
            f"max_abs={max_abs_row.max_abs:.17g} "
            f"worst_abs={max_abs_row.product}:{max_abs_row.variable} "
            f"finite_mismatch={finite_mismatch} nan_mismatch={nan_mismatch} inf_mismatch={inf_mismatch}"
        )
    else:
        print(
            "SUMMARY "
            f"files={common_files} numeric_variables=0 passed=0 failed=0 problems={len(problems)}"
        )


def main() -> int:
    args = _parser().parse_args()
    reference = args.reference.resolve()
    candidate = args.candidate.resolve()
    ref_files = _matches(reference, args.include)
    cand_files = _matches(candidate, args.include)

    problems: list[str] = []
    rows: list[Result] = []
    ref_names, cand_names = set(ref_files), set(cand_files)
    for missing in sorted(ref_names - cand_names):
        problems.append(f"arquivo ausente no candidato: {missing}")
    for extra in sorted(cand_names - ref_names):
        problems.append(f"arquivo extra no candidato: {extra}")

    common = sorted(ref_names & cand_names)
    for relative in common:
        product_rows, product_problems = compare_product(
            ref_files[relative],
            cand_files[relative],
            rtol=args.rtol,
            atol=args.atol,
        )
        rows.extend(replace(row, product=relative) for row in product_rows)
        problems.extend(f"{relative}: {problem}" for problem in product_problems)

    _print_summary(rows, len(common), problems)
    if args.verbose:
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
