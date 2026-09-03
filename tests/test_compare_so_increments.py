from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import netCDF4
import numpy as np


def _write(path: Path, values: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with netCDF4.Dataset(path, "w") as dataset:
        dataset.createDimension("n", len(values))
        variable = dataset.createVariable("u", "f4", ("n",))
        variable[:] = np.asarray(values, dtype=np.float32)


def _script() -> Path:
    return Path(__file__).resolve().parents[1] / "scripts" / "compare_so_increments.py"


def _workspace(root: Path, bg: list[float], analysis: list[float], log: str) -> None:
    _write(root / "bg_so.nc", bg)
    _write(root / "an.2026-06-22_00.00.00.nc", analysis)
    (root / "run_SO.runlog").write_text(log)


def test_so_increment_diagnostic_reports_increment_and_logs(tmp_path: Path) -> None:
    reference = tmp_path / "reference"
    candidate = tmp_path / "candidate"
    _workspace(
        reference,
        [1.0, 2.0],
        [1.1, 2.2],
        "DRPCG iteration 1\ngradient norm reduction = 1e-3\nCostFunction Jb Jo\n",
    )
    _workspace(
        candidate,
        [1.0, 2.0],
        [1.100001, 2.199999],
        "DRPCG iteration 1\ngradient norm reduction = 1e-3\nCostFunction Jb Jo\n",
    )

    result = subprocess.run(
        [sys.executable, str(_script()), str(reference), str(candidate)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "BACKGROUND_STATUS=IDENTICAL" in result.stdout
    assert "INCREMENT variable=u" in result.stdout
    assert "relative_l2=" in result.stdout
    assert "=== SO convergence excerpt: A ===" in result.stdout
    assert "run_SO.runlog" in result.stdout
    assert "A | DRPCG iteration 1" in result.stdout
    assert "B | DRPCG iteration 1" in result.stdout


def test_so_increment_diagnostic_rejects_different_backgrounds(tmp_path: Path) -> None:
    reference = tmp_path / "reference"
    candidate = tmp_path / "candidate"
    _workspace(reference, [1.0, 2.0], [1.1, 2.2], "DRPCG iteration 1\n")
    _workspace(candidate, [1.0, 2.001], [1.1, 2.2], "DRPCG iteration 1\n")

    result = subprocess.run(
        [sys.executable, str(_script()), str(reference), str(candidate)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "BACKGROUND_ERROR u:" in result.stdout
