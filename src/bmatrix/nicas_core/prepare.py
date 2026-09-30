from __future__ import annotations

import shutil
from pathlib import Path

from ..artifacts import StageManifest, read_manifest, require_scientific_identity, scientific_identity, write_manifest
from ..hdiag_core.checks import check as validate_hdiag
from ..hdiag_core.model import hdiag_date
from ..shell import require_file, symlink_force, write_text
from .config_files import write_nicas_merge_files, write_nicas_pbs, write_nicas_yaml
from ..scientific_config import control_file_names
from .model import nicas_workspace
from .static import link_nicas_support


def prepare(config, hdiag_workspace: str | Path, workspace: str | Path | None = None, clean: bool = False) -> Path:
    hdiag_root = Path(hdiag_workspace)
    validate_hdiag(hdiag_root)
    identity = scientific_identity(config)
    require_scientific_identity(read_manifest(hdiag_root, expected_stage="hdiag"), identity)
    hdiag_run = hdiag_root / "HDIAG"
    date = hdiag_date(hdiag_root)
    out = Path(workspace) if workspace else nicas_workspace(config, hdiag_root)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    symlink_force(require_file(hdiag_run / "mpas.cor_rh.nc"), out / "mpas.cor_rh.nc")
    symlink_force(require_file(hdiag_run / "mpas.cor_rv.nc"), out / "mpas.cor_rv.nc")
    symlink_force(require_file(hdiag_run / "mpas.stddev.nc"), out / "mpas.stddev.nc")

    variables = control_file_names(config)
    raw_nvertlevels = config["mesh"].get("nvertlevels")
    if not isinstance(raw_nvertlevels, int) or isinstance(raw_nvertlevels, bool) or raw_nvertlevels <= 0:
        raise ValueError(
            "mesh.nvertlevels must be an explicit positive integer before NICAS preparation."
        )
    for variable in variables:
        run_dir = out / variable
        run_dir.mkdir(parents=True, exist_ok=True)
        link_nicas_support(hdiag_run, run_dir)
        write_nicas_yaml(
            config,
            run_dir / "run_nicas.yaml",
            variable,
            date,
            raw_nvertlevels,
        )
        write_nicas_pbs(config, run_dir, variable)

    write_nicas_merge_files(config, out)
    write_manifest(StageManifest(
        stage="nicas", workspace=str(out.resolve()),
        inputs={"hdiag_workspace": str(hdiag_root.resolve())},
        outputs={"nicas": str((out / "merge" / "mpas_nicas.nc").resolve()), "nicas_norm": str((out / "merge" / "mpas.nicas_norm.nc").resolve()), "dirac_nicas": str((out / "merge" / "mpas.dirac_nicas.nc").resolve())},
        metadata={"variables": list(variables), "date": date, "scientific_identity": identity}, status="prepared",
    ))
    write_text(out / "README.md", f"# NICAS split/merge workspace\n\nHDIAG workspace: `{hdiag_root}`\n")
    print("=== NICAS split/merge workspace ===")
    print(f"WORKSPACE={out}")
    print(f"VARIABLES={','.join(variables)}")
    print(f"MERGE_DIR={out / 'merge'}")
    return out
