from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

from ..shell import require_file
from ..vbal_core.model import covariance_root


def unbalance_workspace(config: Mapping[str, object], vbal_workspace_path: str | Path) -> Path:
    """Resolve the deterministic UNBALANCE workspace for one VBAL run."""
    return covariance_root(config) / "unbalance" / Path(vbal_workspace_path).name


def unbalance_exe(config: Mapping[str, object]) -> Path:
    """Resolve the executable that applies K2^-1 to centered perturbations.

    Resolution order:

    1. explicit platform value ``install.unbalance_executable``;
    2. legacy explicit value ``unbalance.executable``;
    3. conventional ``install.root/bin/mpasjedi_unbalance_ensemble.x``.

    The legacy key remains accepted so an old scientific contract does not
    silently resolve to a different executable merely because ``install.root``
    is also present.
    """
    install = config.get("install", {})
    legacy = config.get("unbalance", {})

    configured: object | None = None
    if isinstance(install, Mapping):
        configured = install.get("unbalance_executable")
    if configured is None and isinstance(legacy, Mapping):
        configured = legacy.get("executable")
    if configured is None and isinstance(install, Mapping) and install.get("root"):
        configured = Path(str(install["root"])) / "bin" / "mpasjedi_unbalance_ensemble.x"
    if configured is None:
        raise ValueError(
            "Configure install.unbalance_executable, unbalance.executable ou "
            "install.root para localizar mpasjedi_unbalance_ensemble.x."
        )
    return require_file(configured, "mpasjedi_unbalance_ensemble.x")


def vbal_date(vbal_root: str | Path) -> str:
    """Read the calibration date from a rendered VBAL YAML file."""
    text = require_file(Path(vbal_root) / "VBAL" / "run_vbal.yaml", "run_vbal.yaml").read_text()
    match = re.search(r"(?m)^\s*date:\s*([^ \n]+)", text)
    if not match:
        raise RuntimeError("Data principal não encontrada no run_vbal.yaml")
    return match.group(1).strip("'\"")
