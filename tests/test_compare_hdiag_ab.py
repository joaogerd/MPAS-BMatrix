from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import netCDF4
import numpy as np


def _module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "compare_hdiag_ab.py"
    spec = importlib.util.spec_from_file_location("compare_hdiag_ab", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _product(path: Path, values: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with netCDF4.Dataset(path, "w") as dataset:
        dataset.createDimension("x", len(values))
        group = dataset.createGroup("diagnostics")
        variable = group.createVariable("temperature", "f8", ("x",))
        variable[:] = np.asarray(values)


def test_compare_product_recurses_groups_and_accepts_roundoff(tmp_path: Path) -> None:
    module = _module()
    reference = tmp_path / "reference" / "mpas.stddev.nc"
    candidate = tmp_path / "candidate" / "mpas.stddev.nc"
    _product(reference, [1.0, 2.0])
    _product(candidate, [1.0 + 1.0e-9, 2.0 - 1.0e-9])

    rows, problems = module.compare_product(
        reference,
        candidate,
        rtol=1.0e-6,
        atol=1.0e-8,
    )

    assert problems == []
    assert len(rows) == 1
    assert rows[0].variable == "diagnostics/temperature"
    assert rows[0].status == "PASS"
    assert rows[0].max_abs > 0.0


def test_compare_product_rejects_scientific_difference(tmp_path: Path) -> None:
    module = _module()
    reference = tmp_path / "reference" / "mpas.cor_rh.nc"
    candidate = tmp_path / "candidate" / "mpas.cor_rh.nc"
    _product(reference, [1.0, 2.0])
    _product(candidate, [1.0, 2.1])

    rows, problems = module.compare_product(
        reference,
        candidate,
        rtol=1.0e-8,
        atol=1.0e-10,
    )

    assert problems == []
    assert rows[0].status == "FAIL"
    assert rows[0].max_abs > 0.09


def test_resolve_product_accepts_hdiag_workspace_root(tmp_path: Path) -> None:
    module = _module()
    product = tmp_path / "HDIAG" / "mpas.cor_rv.nc"
    _product(product, [1.0])

    assert module._resolve_product(tmp_path, "mpas.cor_rv.nc") == product
