from __future__ import annotations

from pathlib import Path

from ..shell import require_file, symlink_force


def link_nicas_support(hdiag_run: Path, run_dir: Path) -> None:
    required = ["bg.nc", "namelist.atmosphere", "streams.atmosphere"]
    for name in required:
        symlink_force(require_file(hdiag_run / name, name), run_dir / name)

    for pattern in [
        "templateFields.*.nc",
        "*.graph.info",
        "*.graph.info.part.*",
        "*.invariant.nc",
        "stream_list.atmosphere.*",
        "geovars.yaml",
        "keptvars.yaml",
        "[A-Z]*",
    ]:
        for source in hdiag_run.glob(pattern):
            symlink_force(source, run_dir / source.name)

