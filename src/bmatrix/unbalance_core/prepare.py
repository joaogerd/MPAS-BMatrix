from __future__ import annotations

import shutil
import hashlib
from pathlib import Path

from ..artifacts import StageManifest, read_manifest, write_manifest
from ..shell import write_text
from ..scheduler import configured_mpi_ranks
from ..vbal_core.validate import validate as validate_vbal
from .config_files import write_unbalance_pbs, write_unbalance_yaml
from .model import unbalance_exe, unbalance_workspace, vbal_date
from .static import link_unbalance_inputs


def _sample_stem(vbal_root: Path) -> str:
    manifest = read_manifest(vbal_root, expected_stage="vbal")
    value = manifest.metadata.get("sample_stem")
    if not isinstance(value, str) or not value:
        raise RuntimeError("Manifesto VBAL não contém sample_stem.")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(config, vbal_workspace_path: str | Path, workspace: str | Path | None = None, clean: bool = False) -> Path:
    """Prepare UNBALANCE from a validated VBAL workspace."""
    vbal_root = Path(vbal_workspace_path)
    validate_vbal(vbal_root)
    sample_stem = _sample_stem(vbal_root)
    samples = sorted((vbal_root / "samples").glob(f"{sample_stem}_*.nc"))
    if not samples:
        raise RuntimeError(f"Nenhuma amostra original encontrada em {vbal_root / 'samples'}")

    out = Path(workspace) if workspace else unbalance_workspace(config, vbal_root)
    if clean and out.exists():
        shutil.rmtree(out)
    run_dir = out / "UNBALANCE"
    run_dir.mkdir(parents=True, exist_ok=True)

    link_unbalance_inputs(vbal_root, out, run_dir)
    date = vbal_date(vbal_root)
    exe = unbalance_exe(config)
    ranks = configured_mpi_ranks(config)
    config_path = str(config.get("bmatrix_contract_path", ""))
    write_unbalance_yaml(config, run_dir / "run_unbalance.yaml", nmembers=len(samples), date=date)
    write_unbalance_pbs(config, run_dir)
    write_manifest(
        StageManifest(
            stage="unbalance",
            workspace=str(out.resolve()),
            inputs={
                "vbal_workspace": str(vbal_root.resolve()),
                "samples": str((out / "samples").resolve()),
                "vbal_global": str((run_dir / "mpas_vbal.nc").resolve()),
                "sampling_global": str((run_dir / "mpas_sampling.nc").resolve()),
            },
            outputs={"samples_unbalanced": str((out / "samplesUnbalanced").resolve())},
            metadata={
                "members": len(samples),
                "date": date,
                "sample_stem": sample_stem,
                "mpi_ranks": ranks,
                "config": config_path,
                "executable": str(exe),
                "executable_sha256": _sha256(exe),
                "executable_build_dir": str(exe.parent.parent),
            },
            status="prepared",
        )
    )
    write_text(
        out / "README.md",
        f"# UNBALANCE workspace\n\nVBAL workspace: `{vbal_root}`\nMembers: {len(samples)}\n"
        f"Samples: `samples/{sample_stem}_%mem%.nc`\nOutput: `samplesUnbalanced/{sample_stem}_%mem%.nc`\n",
    )
    print("=== UNBALANCE workspace ===")
    print(f"WORKSPACE={out}")
    print(f"RUN_DIR={run_dir}")
    print(f"MEMBERS={len(samples)}")
    print(f"YAML={run_dir / 'run_unbalance.yaml'}")
    print(f"PBS={run_dir / 'qsub_unbalance.bash'}")
    return out
