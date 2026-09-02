"""Controlled A/B validation for materialized versus in-memory VBAL inversion.

This module is intentionally outside ``bmatrix.pipeline.STAGES``.  It exists
only to validate the migration from the legacy materialized UNBALANCE path to
the production in-memory ``BUMP_VerticalBalance`` outer block in HDIAG and its
downstream scientific products.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

import yaml

from .artifacts import StageManifest, read_manifest, write_manifest
from .config import load_config
from .dirac_core.runner import prepare as prepare_dirac, submit as submit_dirac, validate as validate_dirac
from .hdiag_core.config_files import write_hdiag_pbs, write_hdiag_yaml
from .hdiag_core.model import require_hdiag_members
from .hdiag_core.prepare import prepare as prepare_in_memory_hdiag
from .hdiag_core.runner import submit as submit_hdiag, validate as validate_hdiag
from .nicas_core.runner import prepare as prepare_nicas, submit as submit_nicas, validate as validate_nicas
from .shell import require_file, symlink_force, write_text
from .so_core.runner import prepare as prepare_so, submit as submit_so, validate as validate_so
from .unbalance_core.model import unbalance_exe
from .unbalance_core.runner import prepare as prepare_unbalance, submit as submit_unbalance, validate as validate_unbalance
from .vbal_core.model import covariance_root, toolbox_exe, vbal_date
from .vbal_core.validate import validate as validate_vbal


@dataclass(frozen=True, slots=True)
class ABPaths:
    root: Path
    materialized_unbalance: Path
    materialized_hdiag: Path
    materialized_nicas: Path
    materialized_so: Path
    materialized_dirac: Path
    in_memory_hdiag: Path
    in_memory_nicas: Path
    in_memory_so: Path
    in_memory_dirac: Path
    comparison_csv: Path
    nicas_comparison_csv: Path
    so_comparison_csv: Path
    dirac_comparison_csv: Path

    def as_dict(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}


def ab_paths(config: Mapping[str, object], vbal_workspace: str | Path, root: str | Path | None = None) -> ABPaths:
    vbal = Path(vbal_workspace).resolve()
    base = Path(root).resolve() if root else covariance_root(config) / "ab_hdiag" / vbal.name
    materialized = base / "materialized"
    in_memory = base / "in-memory"
    return ABPaths(
        root=base,
        materialized_unbalance=materialized / "unbalance",
        materialized_hdiag=materialized / "hdiag",
        materialized_nicas=materialized / "nicas",
        materialized_so=materialized / "so",
        materialized_dirac=materialized / "dirac",
        in_memory_hdiag=in_memory / "hdiag",
        in_memory_nicas=in_memory / "nicas",
        in_memory_so=in_memory / "so",
        in_memory_dirac=in_memory / "dirac",
        comparison_csv=base / "hdiag-ab-comparison.csv",
        nicas_comparison_csv=base / "nicas-ab-comparison.csv",
        so_comparison_csv=base / "so-ab-comparison.csv",
        dirac_comparison_csv=base / "dirac-ab-comparison.csv",
    )


def _vbal_from_unbalance(unbalance_root: Path) -> Path:
    manifest = read_manifest(unbalance_root, expected_stage="unbalance")
    value = manifest.inputs.get("vbal_workspace")
    if not isinstance(value, str) or not value:
        raise RuntimeError("Manifesto UNBALANCE não contém vbal_workspace.")
    return Path(value)


def _sample_stem(unbalance_root: Path) -> str:
    manifest = read_manifest(unbalance_root, expected_stage="unbalance")
    value = manifest.metadata.get("sample_stem")
    if not isinstance(value, str) or not value:
        raise RuntimeError("Manifesto UNBALANCE não contém sample_stem.")
    return value


def write_materialized_hdiag_yaml(
    config: Mapping[str, object],
    path: str | Path,
    nmembers: int,
    date: str,
    sample_stem: str,
) -> None:
    """Render legacy HDIAG by changing only where K2^-1 is evaluated.

    Start from the production HDIAG renderer so every HDIAG/NICAS calibration
    setting remains identical.  The A path then reads the already transformed
    ``samplesUnbalanced`` members and removes the in-memory VBAL outer block.
    """
    destination = Path(path)
    write_hdiag_yaml(config, destination, nmembers, date, sample_stem=sample_stem)
    data = yaml.safe_load(destination.read_text())
    background_error = data["background error"]
    template = background_error["ensemble"]["members from template"]["template"]
    template["filename"] = f"../samplesUnbalanced/{sample_stem}_%mem%.nc"
    background_error.pop("saber outer blocks", None)
    write_text(destination, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def _link_materialized_inputs(unbalance_root: Path, vbal_root: Path, workspace: Path, run_dir: Path) -> None:
    vbal_run = vbal_root / "VBAL"
    symlink_force(unbalance_root / "samplesUnbalanced", workspace / "samplesUnbalanced")
    symlink_force(vbal_run, workspace / "vbal")

    required = ["bg.nc", "namelist.atmosphere_240km", "streams.atmosphere_240km"]
    template_fields = sorted(vbal_run.glob("templateFields.*.nc"))
    if len(template_fields) != 1:
        raise RuntimeError("Esperado exatamente um templateFields.*.nc no workspace VBAL.")

    for name in required:
        symlink_force(require_file(vbal_run / name, name), run_dir / name)
    symlink_force(template_fields[0], run_dir / template_fields[0].name)

    for pattern in [
        "*.graph.info",
        "*.graph.info.part.*",
        "*.invariant.nc",
        "stream_list.atmosphere.*",
        "geovars.yaml",
        "keptvars.yaml",
        "[A-Z]*",
    ]:
        for source in vbal_run.glob(pattern):
            if source.name not in required:
                symlink_force(source, run_dir / source.name)


def prepare_materialized_hdiag(
    config: Mapping[str, object],
    unbalance_workspace: str | Path,
    workspace: str | Path,
    *,
    clean: bool = False,
) -> Path:
    """Prepare the legacy HDIAG reference from materialized K2^-1 members."""
    unbalance_root = Path(unbalance_workspace)
    validate_unbalance(unbalance_root, config)
    vbal_root = _vbal_from_unbalance(unbalance_root)
    sample_stem = _sample_stem(unbalance_root)
    samples = sorted((unbalance_root / "samplesUnbalanced").glob(f"{sample_stem}_*.nc"))
    if not samples:
        raise RuntimeError("Nenhuma amostra materializada encontrada em samplesUnbalanced.")
    require_hdiag_members(samples, int(config.get("hdiag", {}).get("min_members", 4)))

    out = Path(workspace)
    if out.exists():
        if not clean:
            raise RuntimeError(f"Workspace HDIAG materializado já existe: {out}; use --clean para recriá-lo.")
        shutil.rmtree(out)
    run_dir = out / "HDIAG"
    run_dir.mkdir(parents=True, exist_ok=True)

    _link_materialized_inputs(unbalance_root, vbal_root, out, run_dir)
    date = vbal_date(vbal_root)
    write_materialized_hdiag_yaml(config, run_dir / "run_hdiag.yaml", len(samples), date, sample_stem)
    write_hdiag_pbs(config, run_dir)
    write_manifest(
        StageManifest(
            stage="hdiag",
            workspace=str(out.resolve()),
            inputs={
                "mode": "materialized-reference",
                "unbalance_workspace": str(unbalance_root.resolve()),
                "vbal_workspace": str(vbal_root.resolve()),
            },
            outputs={
                "stddev": str((run_dir / "mpas.stddev.nc").resolve()),
                "cor_rh": str((run_dir / "mpas.cor_rh.nc").resolve()),
                "cor_rv": str((run_dir / "mpas.cor_rv.nc").resolve()),
            },
            metadata={"members": len(samples), "date": date, "sample_stem": sample_stem},
            status="prepared",
        )
    )
    write_text(
        out / "README.md",
        "# HDIAG A/B materialized reference\n\n"
        f"UNBALANCE workspace: `{unbalance_root}`\n"
        f"VBAL workspace: `{vbal_root}`\n"
        f"Members: {len(samples)}\n"
        f"Samples: `samplesUnbalanced/{sample_stem}_%mem%.nc`\n",
    )
    return out


def _require_fresh(path: Path, clean: bool, label: str) -> None:
    if path.exists() and not clean:
        raise RuntimeError(f"{label} já existe: {path}; use --clean para recriar explicitamente.")


def run_reference(config: Mapping[str, object], vbal: Path, paths: ABPaths, *, clean: bool, poll_seconds: int) -> None:
    validate_vbal(vbal)
    _require_fresh(paths.materialized_unbalance, clean, "Workspace UNBALANCE A/B")
    prepare_unbalance(config, vbal, workspace=paths.materialized_unbalance, clean=clean)
    submit_unbalance(paths.materialized_unbalance, wait=True, poll_seconds=poll_seconds)
    validate_unbalance(paths.materialized_unbalance, config)

    prepare_materialized_hdiag(
        config,
        paths.materialized_unbalance,
        paths.materialized_hdiag,
        clean=clean,
    )
    submit_hdiag(paths.materialized_hdiag, wait=True, poll_seconds=poll_seconds)
    validate_hdiag(paths.materialized_hdiag)


def run_candidate(config: Mapping[str, object], vbal: Path, paths: ABPaths, *, clean: bool, poll_seconds: int) -> None:
    validate_vbal(vbal)
    _require_fresh(paths.in_memory_hdiag, clean, "Workspace HDIAG in-memory A/B")
    prepare_in_memory_hdiag(config, vbal, workspace=paths.in_memory_hdiag, clean=clean)
    submit_hdiag(paths.in_memory_hdiag, wait=True, poll_seconds=poll_seconds)
    validate_hdiag(paths.in_memory_hdiag)


def compare(paths: ABPaths, *, rtol: float, atol: float) -> int:
    script = Path(__file__).resolve().parents[2] / "scripts" / "compare_hdiag_ab.py"
    require_file(script, "scripts/compare_hdiag_ab.py")
    command = [
        sys.executable,
        str(script),
        str(paths.materialized_hdiag),
        str(paths.in_memory_hdiag),
        "--rtol",
        str(rtol),
        "--atol",
        str(atol),
        "--output",
        str(paths.comparison_csv),
    ]
    return subprocess.run(command, check=False).returncode


def _branch_paths(paths: ABPaths, branch: str) -> tuple[Path, Path, Path, Path]:
    if branch == "materialized":
        return paths.materialized_hdiag, paths.materialized_nicas, paths.materialized_so, paths.materialized_dirac
    if branch == "in-memory":
        return paths.in_memory_hdiag, paths.in_memory_nicas, paths.in_memory_so, paths.in_memory_dirac
    raise ValueError(f"branch A/B inválido: {branch}")


def run_downstream(
    config: Mapping[str, object],
    vbal: Path,
    paths: ABPaths,
    *,
    branch: str,
    clean: bool,
    poll_seconds: int,
    nicas_parallel: bool,
    so_variant: str,
) -> None:
    """Run NICAS, SO and DIRAC from one already validated A/B HDIAG branch."""
    hdiag, nicas, so, dirac = _branch_paths(paths, branch)
    validate_vbal(vbal)
    validate_hdiag(hdiag)

    _require_fresh(nicas, clean, f"Workspace NICAS {branch} A/B")
    prepare_nicas(config, hdiag, workspace=nicas, clean=clean)
    submit_nicas(nicas, wait=True, poll_seconds=poll_seconds, parallel=nicas_parallel)
    validate_nicas(nicas)

    _require_fresh(so, clean, f"Workspace SO {branch} A/B")
    prepare_so(config, nicas, hdiag, vbal, workspace=so, clean=clean, variant=so_variant)
    submit_so(so, wait=True, poll_seconds=poll_seconds, variant=so_variant)
    validate_so(so, variant=so_variant)

    _require_fresh(dirac, clean, f"Workspace DIRAC {branch} A/B")
    prepare_dirac(config, nicas, hdiag, vbal, workspace=dirac, clean=clean)
    submit_dirac(dirac, wait=True, poll_seconds=poll_seconds)
    validate_dirac(dirac)


def _compare_tree(
    reference: Path,
    candidate: Path,
    includes: tuple[str, ...],
    output: Path,
    *,
    rtol: float,
    atol: float,
) -> int:
    script = Path(__file__).resolve().parents[2] / "scripts" / "compare_netcdf_trees.py"
    require_file(script, "scripts/compare_netcdf_trees.py")
    command = [
        sys.executable,
        str(script),
        str(reference),
        str(candidate),
        "--rtol",
        str(rtol),
        "--atol",
        str(atol),
        "--output",
        str(output),
    ]
    for pattern in includes:
        command.extend(["--include", pattern])
    return subprocess.run(command, check=False).returncode


def compare_downstream(paths: ABPaths, *, rtol: float, atol: float) -> int:
    """Compare complete NICAS products, DIRAC response and SO analyses."""
    comparisons = [
        (
            "NICAS",
            paths.materialized_nicas,
            paths.in_memory_nicas,
            (
                "*/mpas_nicas.nc",
                "*/mpas.nicas_norm.nc",
                "*/mpas.dirac_nicas.nc",
                "*/mpas_nicas_local_*",
                "*/mpas_nicas_grids_local_*",
            ),
            paths.nicas_comparison_csv,
        ),
        (
            "SO analysis",
            paths.materialized_so,
            paths.in_memory_so,
            ("an.*.nc",),
            paths.so_comparison_csv,
        ),
        (
            "DIRAC",
            paths.materialized_dirac,
            paths.in_memory_dirac,
            ("mpas.dirac.nc",),
            paths.dirac_comparison_csv,
        ),
    ]
    returncode = 0
    for label, reference, candidate, includes, output in comparisons:
        print(f"=== {label} A/B comparison ===")
        code = _compare_tree(reference, candidate, includes, output, rtol=rtol, atol=atol)
        returncode = max(returncode, code)
    return returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Controlled A/B validation; never part of production STAGES.")
    parser.add_argument(
        "phase",
        choices=(
            "plan",
            "reference",
            "candidate",
            "compare",
            "downstream-reference",
            "downstream-candidate",
            "compare-downstream",
        ),
    )
    parser.add_argument("--config", default="configs/jaci-x1.10242.yaml")
    parser.add_argument("--vbal-workspace", type=Path, required=True)
    parser.add_argument("--root", type=Path, help="Optional isolated A/B root.")
    parser.add_argument("--clean", action="store_true", help="Explicitly recreate the selected A/B workspace.")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--nicas-parallel", action="store_true", help="Submit NICAS variables in parallel for both A/B paths.")
    parser.add_argument("--so-variant", default="default", choices=("default", "t-only", "u-only"))
    parser.add_argument("--rtol", type=float, default=1.0e-6)
    parser.add_argument("--atol", type=float, default=1.0e-8)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    vbal = args.vbal_workspace.resolve()
    validate_vbal(vbal)
    paths = ab_paths(config, vbal, args.root)

    if args.phase == "plan":
        report = {
            "production_pipeline_unchanged": True,
            "vbal_workspace": str(vbal),
            "toolbox_executable": str(toolbox_exe(config)),
            "legacy_unbalance_executable": str(unbalance_exe(config)),
            "paths": paths.as_dict(),
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.phase == "reference":
        run_reference(config, vbal, paths, clean=args.clean, poll_seconds=args.poll_seconds)
        print(json.dumps({"reference": str(paths.materialized_hdiag)}, indent=2))
        return 0
    if args.phase == "candidate":
        run_candidate(config, vbal, paths, clean=args.clean, poll_seconds=args.poll_seconds)
        print(json.dumps({"candidate": str(paths.in_memory_hdiag)}, indent=2))
        return 0
    if args.phase == "compare":
        return compare(paths, rtol=args.rtol, atol=args.atol)
    if args.phase == "downstream-reference":
        run_downstream(
            config,
            vbal,
            paths,
            branch="materialized",
            clean=args.clean,
            poll_seconds=args.poll_seconds,
            nicas_parallel=args.nicas_parallel,
            so_variant=args.so_variant,
        )
        print(json.dumps({"downstream_reference": str(paths.materialized_nicas.parent)}, indent=2))
        return 0
    if args.phase == "downstream-candidate":
        run_downstream(
            config,
            vbal,
            paths,
            branch="in-memory",
            clean=args.clean,
            poll_seconds=args.poll_seconds,
            nicas_parallel=args.nicas_parallel,
            so_variant=args.so_variant,
        )
        print(json.dumps({"downstream_candidate": str(paths.in_memory_nicas.parent)}, indent=2))
        return 0
    if args.phase == "compare-downstream":
        return compare_downstream(paths, rtol=args.rtol, atol=args.atol)
    raise AssertionError(args.phase)


if __name__ == "__main__":
    raise SystemExit(main())
