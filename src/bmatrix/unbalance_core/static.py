from __future__ import annotations

from pathlib import Path

from ..shell import require_file, symlink_force


def link_unbalance_inputs(vbal_root: Path, workspace: Path, run_dir: Path) -> None:
    """Link MPAS runtime and VBAL products into the isolated UNBALANCE workspace."""
    vbal_run = vbal_root / "VBAL"
    symlink_force(vbal_root / "samples", workspace / "samples")
    (workspace / "samplesUnbalanced").mkdir(parents=True, exist_ok=True)
    symlink_force(vbal_run, workspace / "vbal")

    required = ["bg.nc", "namelist.atmosphere", "streams.atmosphere"]
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
        "mpas_sampling.nc",
        "mpas_sampling_local_*.nc",
        "mpas_vbal.nc",
        "mpas_vbal_local_*.nc",
    ]:
        for source in vbal_run.glob(pattern):
            if source.name not in required:
                symlink_force(source, run_dir / source.name)


