from __future__ import annotations
import csv
from pathlib import Path
import netCDF4
import numpy as np
import pytest
from bmatrix.nmc_core.checks import validate_manifest
from bmatrix.nmc_core.manifest import ManifestError

REQUIRED = ["theta","uReconstructZonal","uReconstructMeridional","surface_pressure","qv","qc","qr","qi","qs","qg","pressure_p","pressure_base"]

def _state(path: Path, valid_time: str, n_cells: int = 3, omit: str | None = None, shift_mesh: bool = False) -> None:
    with netCDF4.Dataset(path, "w", format="NETCDF4") as ds:
        ds.createDimension("Time", 1); ds.createDimension("nCells", n_cells)
        ds.createDimension("nVertLevels", 2); ds.createDimension("StrLen", len(valid_time) + 2)
        xtime = ds.createVariable("xtime", "S1", ("Time", "StrLen"))
        xtime[:] = np.asarray([list(valid_time + "  ")], dtype="S1")
        lat = ds.createVariable("latCell", "f8", ("nCells",))
        lon = ds.createVariable("lonCell", "f8", ("nCells",))
        lat[:] = np.linspace(-0.2, 0.2, n_cells) + (0.01 if shift_mesh else 0.0)
        lon[:] = np.linspace(0.1, 0.5, n_cells)
        for name in REQUIRED:
            if name == omit: continue
            dims = ("Time","nCells") if name == "surface_pressure" else ("Time","nCells","nVertLevels")
            ds.createVariable(name, "f4", dims)

def _config(mesh: Path):
    return {"mesh":{"name":"x1.test","grid":str(mesh)},"bflow":{"wind_transform":{"zonal_file_variable":"uReconstructZonal","meridional_file_variable":"uReconstructMeridional","template_file_variable":"theta"},"copy_variables":REQUIRED[1:],"derived_variables":[{"inputs":["pressure_p","pressure_base"],"template_file":"pressure_p"},{"theta_file":"theta","template_file":"theta"},{"mixing_ratio_file":"qv","template_file":"qv"}]}}

def _canonical_mesh(tmp_path: Path) -> Path:
    path = tmp_path / "mesh.nc"
    _state(path, "2000-01-01_00:00:00")
    return path

def _manifest(tmp_path: Path, omit=None, mismatch=False, wrong_time=False, shift_mesh=False):
    path=tmp_path/"legacy.tsv"
    with path.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.writer(stream,delimiter="\t"); writer.writerow(["valid_time","f048","f024"])
        for i in range(4):
            valid=f"2018-04-{i+1:02d}_00:00:00"; f48=tmp_path/f"f48-{i}.nc"; f24=tmp_path/f"f24-{i}.nc"
            _state(f48,"1999-01-01_00:00:00" if wrong_time and i==0 else valid,omit=omit if i==0 else None,shift_mesh=shift_mesh and i==0)
            _state(f24,valid,n_cells=4 if mismatch and i==0 else 3); writer.writerow([valid,f48,f24])
    return path

def test_accepts_compatible_pairs(tmp_path):
    report=validate_manifest(_manifest(tmp_path),config=_config(_canonical_mesh(tmp_path)))
    assert report["scientific_contract_verified"] is True
    assert report["scientific_contract"]["mesh_shape"] == [3,2]

def test_rejects_missing_variable(tmp_path):
    with pytest.raises(ManifestError,match="theta"): validate_manifest(_manifest(tmp_path,omit="theta"),config=_config(_canonical_mesh(tmp_path)))

def test_rejects_wrong_valid_time(tmp_path):
    with pytest.raises(ManifestError,match="xtime"): validate_manifest(_manifest(tmp_path,wrong_time=True),config=_config(_canonical_mesh(tmp_path)))

def test_rejects_pair_mesh_mismatch(tmp_path):
    with pytest.raises(ManifestError,match="canonical mesh"): validate_manifest(_manifest(tmp_path,mismatch=True),config=_config(_canonical_mesh(tmp_path)))


def test_rejects_same_size_but_different_mesh_geometry(tmp_path):
    with pytest.raises(ManifestError, match="canonical MPAS mesh"):
        validate_manifest(
            _manifest(tmp_path, shift_mesh=True),
            config=_config(_canonical_mesh(tmp_path)),
        )

def test_reports_canonical_mesh_fingerprint(tmp_path):
    report = validate_manifest(
        _manifest(tmp_path),
        config=_config(_canonical_mesh(tmp_path)),
    )
    identity = report["scientific_contract"]["mesh_identity"]
    assert identity["name"] == "x1.test"
    assert identity["nCells"] == 3
    assert len(identity["geometry_sha256"]) == 64
