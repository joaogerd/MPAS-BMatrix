from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import netCDF4
import numpy as np


def _write(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with netCDF4.Dataset(path, "w") as dataset:
        dataset.createDimension("n", values.size)
        variable = dataset.createVariable("field", "f4", ("n",))
        variable[:] = values


def _script() -> Path:
    return Path(__file__).resolve().parents[1] / "scripts" / "compare_netcdf_trees.py"


def test_compare_netcdf_trees_accepts_float32_roundoff(tmp_path: Path) -> None:
    reference = tmp_path / "reference"
    candidate = tmp_path / "candidate"
    base = np.asarray([1.0, 2.0, 3.0], dtype=np.float32)
    rounded = np.nextafter(base, np.float32(np.inf), dtype=np.float32)
    _write(reference / "merge" / "product.nc", base)
    _write(candidate / "merge" / "product.nc", rounded)
    output = tmp_path / "comparison.csv"

    result = subprocess.run(
        [
            sys.executable,
            str(_script()),
            str(reference),
            str(candidate),
            "--include",
            "merge/*.nc",
            "--rtol",
            "2e-7",
            "--atol",
            "0",
            "--output",
            str(output),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout
    assert output.is_file()


def test_compare_netcdf_trees_rejects_missing_product(tmp_path: Path) -> None:
    reference = tmp_path / "reference"
    candidate = tmp_path / "candidate"
    values = np.asarray([1.0], dtype=np.float32)
    _write(reference / "merge" / "product.nc", values)
    candidate.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            str(_script()),
            str(reference),
            str(candidate),
            "--include",
            "merge/*.nc",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "arquivo ausente no candidato: merge/product.nc" in result.stderr
