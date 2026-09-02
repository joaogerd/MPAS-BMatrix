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
    return parser


def _matches(root: Path, patterns: list[str]) -> dict[str, Path]:
    matches: dict[str, Path] = {}
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file():
                matches[str(path.relative_to(root))] = path
    return matches


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

    for relative in sorted(ref_names & cand_names):
        product_rows, product_problems = compare_product(
            ref_files[relative],
            cand_files[relative],
            rtol=args.rtol,
            atol=args.atol,
        )
        rows.extend(replace(row, product=relative) for row in product_rows)
        problems.extend(f"{relative}: {problem}" for problem in product_problems)

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
