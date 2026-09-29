from __future__ import annotations
import csv
from pathlib import Path
import netCDF4
import numpy as np
import pytest
from bmatrix.nmc_core.checks import validate_manifest
from bmatrix.nmc_core.manifest import ManifestError

REQUIRED = ["theta","uReconstructZonal","uReconstructMeridional","surface_pressure","qv","qc","qr","qi","qs","qg","pressure_p","pressure_base"]

def _state(path: Path, valid_time: str, n_cells: int = 3, omit: str | None = None) -> None:
    with netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_DATA") as ds:
        ds.createDimension("Time", 1); ds.createDimension("nCells", n_cells)
        ds.createDimension("nVertLevels", 2); ds.createDimension("StrLen", 64)
        xtime = ds.createVariable("xtime", "S1", ("Time", "StrLen"))
        xtime[:] = netCDF4.stringtochar(np.asarray([valid_time], dtype="S64"))
        for name in REQUIRED:
            if name == omit: continue
            dims = ("Time","nCells") if name == "surface_pressure" else ("Time","nCells","nVertLevels")
            ds.createVariable(name, "f4", dims)

def _config():
    return {"bflow":{"wind_transform":{"zonal_file_variable":"uReconstructZonal","meridional_file_variable":"uReconstructMeridional","template_file_variable":"theta"},"copy_variables":REQUIRED[1:],"derived_variables":[{"inputs":["pressure_p","pressure_base"],"template_file":"pressure_p"},{"theta_file":"theta","template_file":"theta"},{"mixing_ratio_file":"qv","template_file":"qv"}]}}

def _manifest(tmp_path: Path, omit=None, mismatch=False, wrong_time=False):
    path=tmp_path/"legacy.tsv"
    with path.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.writer(stream,delimiter="\t"); writer.writerow(["valid_time","f048","f024"])
        for i in range(4):
            valid=f"2018-04-{i+1:02d}_00:00:00"; f48=tmp_path/f"f48-{i}.nc"; f24=tmp_path/f"f24-{i}.nc"
            _state(f48,"1999-01-01_00:00:00" if wrong_time and i==0 else valid,omit=omit if i==0 else None)
            _state(f24,valid,n_cells=4 if mismatch and i==0 else 3); writer.writerow([valid,f48,f24])
    return path

def test_accepts_compatible_pairs(tmp_path):
    report=validate_manifest(_manifest(tmp_path),config=_config())
    assert report["scientific_contract_verified"] is True
    assert report["scientific_contract"]["mesh_shape"] == [3,2]

def test_rejects_missing_variable(tmp_path):
    with pytest.raises(ManifestError,match="theta"): validate_manifest(_manifest(tmp_path,omit="theta"),config=_config())

def test_rejects_wrong_valid_time(tmp_path):
    with pytest.raises(ManifestError,match="xtime"): validate_manifest(_manifest(tmp_path,wrong_time=True),config=_config())

def test_rejects_pair_mesh_mismatch(tmp_path):
    with pytest.raises(ManifestError,match="incompatible MPAS grids"): validate_manifest(_manifest(tmp_path,mismatch=True),config=_config())
