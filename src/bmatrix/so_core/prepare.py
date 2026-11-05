"""Preparation of a Single Observation validation workspace."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Mapping

from ..artifacts import StageManifest, write_manifest
from ..hdiag_core.checks import check as validate_hdiag
from ..hdiag_core.model import hdiag_date
from ..nicas_core.checks import check as validate_nicas
from ..products import BMatrixProducts
from ..scientific_config import require_background_covers_analysis, section
from ..shell import require_file, write_text
from ..vbal_core.validate import validate as validate_vbal
from .config_files import write_so_pbs, write_so_t_only_diagnostic_pbs, write_so_yaml
from .checks import MPAS_ANALYSIS_VARIABLES
from .model import so_artifacts, so_workspace
from .static import create_so_background, link_so_support


def prepare(
    config: Mapping[str, object],
    nicas_workspace: str | Path,
    hdiag_workspace: str | Path,
    vbal_workspace: str | Path,
    workspace: str | Path | None = None,
    clean: bool = False,
    variant: str = "default",
    debug_core: bool = False,
) -> Path:
    """Prepare SO from explicit upstream artifact workspaces.

    Unlike the previous implementation, upstream locations are mandatory
    arguments.  Runtime discovery never parses README prose.
    """
    artifacts = so_artifacts(variant)
    nicas_root, hdiag_root, vbal_root = Path(nicas_workspace), Path(hdiag_workspace), Path(vbal_workspace)
    validate_nicas(nicas_root)
    validate_hdiag(hdiag_root)
    validate_vbal(vbal_root)
    products = BMatrixProducts.from_workspaces(
        vbal_workspace=vbal_root, hdiag_workspace=hdiag_root, nicas_workspace=nicas_root
    )
    for path in products.required_for_assimilation():
        require_file(path, f"produto B: {path.name}")

    output = Path(workspace) if workspace else so_workspace(config, nicas_root)
    if clean and output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    template = link_so_support(hdiag_root / "HDIAG", output)
    single = section(config, "single_observation")
    background_variables = require_background_covers_analysis(
        single.get("background_variables", []),
        single.get("analysis_variables", []),
        "single_observation",
    )
    native_fields = single.get("validation_native_analysis_fields", MPAS_ANALYSIS_VARIABLES)
    if not isinstance(native_fields, list) or not all(
        isinstance(name, str) and name.strip() for name in native_fields
    ):
        raise ValueError(
            "single_observation.validation_native_analysis_fields deve listar "
            "os nomes nativos MPAS esperados no arquivo de análise."
        )
    create_so_background(template, output / "bg_so.nc", background_variables)
    write_so_yaml(config, output / artifacts["yaml"], hdiag_date(hdiag_root), products.nicas.parent, products.stddev, products.vbal.parent, variant=variant)
    write_so_pbs(config, output, variant=variant)
    if debug_core:
        if variant != "t-only":
            raise ValueError("--debug-core é restrito à variante t-only.")
        write_so_t_only_diagnostic_pbs(config, output)
    write_manifest(
        StageManifest(
            stage="so",
            workspace=str(output.resolve()),
            inputs={"nicas_workspace": str(nicas_root.resolve()), "hdiag_workspace": str(hdiag_root.resolve()), "vbal_workspace": str(vbal_root.resolve())},
            outputs={"background": str((output / "bg_so.nc").resolve()), "yaml": str((output / artifacts["yaml"]).resolve())},
            metadata={"variant": variant, "required_native_analysis_fields": native_fields},
            status="prepared",
        )
    )
    write_text(output / "README.md", "# Single Observation workspace\n\nMachine-readable provenance: `stage-manifest.json`.\n")
    return output
