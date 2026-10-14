from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Mapping

from xml.etree import ElementTree as ET

from ..scientific_config import bflow_sample_stem, control_file_names
from ..shell import require_file, symlink_force, write_text
from .model import TIME_FORMAT, Sample


def write_stream_list_control(config: Mapping[str, object], path: Path) -> None:
    """Write the MPAS control stream list from the declared controls."""
    write_text(path, "\n".join(control_file_names(config)) + "\n")


def stage_samples(config: Mapping[str, object], workspace: Path, samples: list[Sample]) -> str:
    """Link CDF5 BFLOW perturbations into the canonical numbered VBAL sample layout.

    BFLOW is the sole producer responsible for the CDF5 format.  VBAL only
    creates deterministic member aliases and must not recode NetCDF products.

    Returns
    -------
    str
        Filename stem used by all downstream ensemble templates.
    """
    samples_dir = workspace / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    stem = bflow_sample_stem(config)
    for index, sample in enumerate(samples, start=1):
        member = f"{index:03d}"
        destination = samples_dir / f"{stem}_{member}.nc"
        symlink_force(sample.ptb, destination)
    return stem


def link_static_files(
    config: Mapping[str, object], run_dir: Path, bg_file: Path, template_fields: Path, valid_time: str
) -> None:
    """Link static MPAS/JEDI support files needed by a covariance toolbox run."""
    mesh = config["mesh"]
    static = config["static"]
    if not isinstance(mesh, Mapping) or not isinstance(static, Mapping):
        raise ValueError("mesh e static devem ser blocos YAML.")
    support = static.get("support_dir", static.get("tutorial_physics_files"))
    if support is None:
        raise ValueError("Declare static.support_dir for MPAS stream lists and support files.")
    tutorial = Path(str(support))

    symlink_force(mesh["graph"], run_dir / Path(str(mesh["graph"])).name)
    partition = Path(str(mesh["partitions_dir"])) / f"{Path(str(mesh['graph'])).name}.part.{int(mesh['nproc'])}"
    symlink_force(require_file(partition, "mesh partition"), run_dir / partition.name)

    symlink_force(static["invariant"], run_dir / f"{mesh['name']}.invariant.nc")
    symlink_force(bg_file, run_dir / "bg.nc")
    mesh_id = str(mesh["name"]).removeprefix("x1.")
    symlink_force(template_fields, run_dir / f"templateFields.{mesh_id}.nc")

    def source_path(key: str, name: str) -> Path:
        if key in static:
            return require_file(static[key], f"static.{key}")
        neutral = tutorial / name
        if neutral.is_file():
            return neutral
        if str(mesh['name']) != "x1.10242":
            raise ValueError(f"Declare static.{key} for this mesh; tutorial 240-km fallback is disabled.")
        # Backward-compatible input names; never used as downstream aliases.
        return require_file(tutorial / f"{name}_240km", f"static.{key}")

    namelist = source_path("namelist", "namelist.atmosphere")
    text = namelist.read_text()
    start_time = datetime.strptime(valid_time, TIME_FORMAT).strftime("%Y-%m-%d_%H:%M:%S")
    text, replacements = re.subn(
        r"(?m)^(\s*config_start_time\s*=\s*)'[^']+'",
        rf"\g<1>'{start_time}'", text, count=1,
    )
    if replacements != 1:
        raise RuntimeError(f"config_start_time não encontrado em {namelist}")
    text = re.sub(r"(?m)^(\s*config_block_decomp_file_prefix\s*=\s*)'[^']*'",
                  rf"\g<1>'{Path(str(mesh['graph'])).name}.part.'", text)
    destination = run_dir / "namelist.atmosphere"
    if destination.is_symlink():
        destination.unlink()
    write_text(destination, text)

    streams = source_path("streams", "streams.atmosphere")
    tree = ET.parse(streams)
    for stream in tree.getroot():
        if stream.get("name") == "invariant":
            stream.set("filename_template", f"{mesh['name']}.invariant.nc")
    destination = run_dir / "streams.atmosphere"
    if destination.is_symlink():
        destination.unlink()
    tree.write(destination, encoding="unicode")

    install = config.get("install", {})
    physics_dir = Path(str(install.get("atmosphere_share", tutorial))) if isinstance(install, Mapping) else tutorial
    for source in physics_dir.iterdir():
        if source.is_file() and source.name[:1].isupper():
            symlink_force(source, run_dir / source.name)

    for key in ["geovars", "keptvars"]:
        if key in static:
            source = require_file(static[key], key)
            symlink_force(source, run_dir / source.name)

    for source in tutorial.glob("stream_list.atmosphere.*"):
        if source.name != "stream_list.atmosphere.control":
            symlink_force(source, run_dir / source.name)
    write_stream_list_control(config, run_dir / "stream_list.atmosphere.control")

