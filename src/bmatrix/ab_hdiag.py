"""Controlled A/B validation for materialized versus in-memory VBAL inversion.

This module is intentionally outside ``bmatrix.pipeline.STAGES``.  It exists
only to validate the migration from the legacy materialized UNBALANCE path to
the production in-memory ``BUMP_VerticalBalance`` outer block in HDIAG.
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
from .hdiag_core.config_files import write_hdiag_pbs, write_hdiag_yaml
from .hdiag_core.model import require_hdiag_members
from .hdiag_core.runner import submit as submit_hdiag, validate as validate_hdiag
from .hdiag_core.prepare import prepare as prepare_in_memory_hdiag
from .shell import require_file, symlink_force, write_text
from .unbalance_core.model import unbalance_exe
from .unbalance_core.runner import prepare as prepare_unbalance, submit as submit_unbalance, validate as validate_unbalance
from .vbal_core.model import covariance_root, toolbox_exe, vbal_date
from .vbal_core.validate import validate as validate_vbal


@dataclass(frozen=True, slots=True)
class ABPaths:
    root: Path
    materialized_unbalance: Path
    materialized_hdiag: Path
    in_memory_hdiag: Path
    comparison_csv: Path

    def as_dict(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}


def ab_paths(config: Mapping[str, object], vbal_workspace: str | Path, root: str | Path | None = None) -> ABPaths:
    vbal = Path(vbal_workspace).resolve()
    base = Path(root).resolve() if root else covariance_root(config) / "ab_hdiag" / vbal.name
    return ABPaths(
        root=base,
        materialized_unbalance=base / "materialized" / "unbalance",
        materialized_hdiag=base / "materialized" / "hdiag",
        in_memory_hdiag=base / "in-memory" / "hdiag",
        comparison_csv=base / "hdiag-ab-comparison.csv",
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Controlled HDIAG A/B validation; never part of production STAGES.")
    parser.add_argument("phase", choices=("plan", "reference", "candidate", "compare"))
    parser.add_argument("--config", default="configs/jaci-x1.10242.yaml")
    parser.add_argument("--vbal-workspace", type=Path, required=True)
    parser.add_argument("--root", type=Path, help="Optional isolated A/B root.")
    parser.add_argument("--clean", action="store_true", help="Explicitly recreate the selected A/B workspace.")
    parser.add_argument("--poll-seconds", type=int, default=30)
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
    raise AssertionError(args.phase)


if __name__ == "__main__":
    raise SystemExit(main())
