#!/usr/bin/env python3
"""Compare selected NetCDF products under two validation workspaces."""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
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


def _family(product: str) -> str:
    parts = Path(product).parts
    return parts[0] if len(parts) > 1 else "root"


def _print_failure_details(rows: list[Result]) -> None:
    failing = [row for row in rows if row.status != "PASS"]
    if not failing:
        return

    groups: dict[str, list[Result]] = defaultdict(list)
    for row in failing:
        groups[_family(row.product)].append(row)

    ranked_groups = sorted(
        groups.items(),
        key=lambda item: max(row.max_scaled_error for row in item[1]),
        reverse=True,
    )
    for family, group_rows in ranked_groups[:10]:
        failed_elements = sum(row.fail_count for row in group_rows)
        total_elements = sum(row.n_values for row in group_rows)
        worst = max(group_rows, key=lambda row: row.max_scaled_error)
        print(
            "FAIL_GROUP "
            f"family={family} failed_rows={len(group_rows)} "
            f"failed_elements={failed_elements} total_elements={total_elements} "
            f"max_scaled_error={worst.max_scaled_error:.17g} "
            f"worst={worst.product}:{worst.variable}"
        )

    for row in sorted(failing, key=lambda item: item.max_scaled_error, reverse=True)[:8]:
        print(
            "TOP_FAIL "
            f"product={row.product} variable={row.variable} dtype={row.dtype} "
            f"failed_elements={row.fail_count}/{row.n_values} "
            f"fail_fraction={row.fail_fraction:.17g} "
            f"max_scaled_error={row.max_scaled_error:.17g} "
            f"worst_ref={row.worst_ref:.17g} "
            f"worst_candidate={row.worst_candidate:.17g} "
            f"worst_abs_delta={row.worst_abs_delta:.17g} "
            f"max_abs={row.max_abs:.17g} rms={row.rms:.17g} max_rel={row.max_rel:.17g}"
        )


def _print_summary(rows: list[Result], common_files: int, problems: list[str]) -> None:
    passed = sum(row.status == "PASS" for row in rows)
    failed = len(rows) - passed
    status = "PASS" if rows and failed == 0 and not problems else "FAIL"
    if rows:
        worst_rel = max(rows, key=lambda row: row.max_rel)
        worst_abs = max(rows, key=lambda row: row.max_abs)
        worst_scaled = max(rows, key=lambda row: row.max_scaled_error)
        finite_mismatch = sum(row.finite_mismatch for row in rows)
        nan_mismatch = sum(row.nan_mismatch for row in rows)
        inf_mismatch = sum(row.inf_mismatch for row in rows)
        total_values = sum(row.n_values for row in rows)
        failed_elements = sum(row.fail_count for row in rows)
        failed_fraction = failed_elements / total_values if total_values else 0.0
        print(
            "SUMMARY "
            f"status={status} files={common_files} numeric_variables={len(rows)} "
            f"passed={passed} failed={failed} problems={len(problems)} "
            f"elements={total_values} failed_elements={failed_elements} "
            f"failed_fraction={failed_fraction:.17g} "
            f"max_scaled_error={worst_scaled.max_scaled_error:.17g} "
            f"worst_scaled={worst_scaled.product}:{worst_scaled.variable} "
            f"max_rel={worst_rel.max_rel:.17g} "
            f"worst_rel={worst_rel.product}:{worst_rel.variable} "
            f"max_abs={worst_abs.max_abs:.17g} "
            f"worst_abs={worst_abs.product}:{worst_abs.variable} "
            f"finite_mismatch={finite_mismatch} nan_mismatch={nan_mismatch} inf_mismatch={inf_mismatch}"
        )
        _print_failure_details(rows)
    else:
        print(
            "SUMMARY "
            f"status={status} files={common_files} numeric_variables=0 "
            f"passed=0 failed=0 problems={len(problems)}"
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
