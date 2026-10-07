from __future__ import annotations
import csv
from pathlib import Path
import netCDF4
import numpy as np
import pytest
from bmatrix.nmc_core.checks import validate_manifest
from bmatrix.nmc_core.manifest import ManifestError

REQUIRED = ["theta","uReconstructZonal","uReconstructMeridional","surface_pressure","qv","qc","qr","qi","qs","qg","pressure_p","pressure_base"]

def _state(path: Path, valid_time: str, n_cells: int = 3, omit: str | None = None, shift_mesh: bool = False, coordinates: tuple[str, ...] = ("latCell", "lonCell")) -> None:
    with netCDF4.Dataset(path, "w", format="NETCDF4") as ds:
        ds.createDimension("Time", 1); ds.createDimension("nCells", n_cells)
        ds.createDimension("nVertLevels", 2); ds.createDimension("StrLen", len(valid_time) + 2)
        xtime = ds.createVariable("xtime", "S1", ("Time", "StrLen"))
        xtime[:] = np.asarray([list(valid_time + "  ")], dtype="S1")
        if "latCell" in coordinates:
            lat = ds.createVariable("latCell", "f8", ("nCells",))
            lat[:] = np.linspace(-0.2, 0.2, n_cells) + (0.01 if shift_mesh else 0.0)
        if "lonCell" in coordinates:
            lon = ds.createVariable("lonCell", "f8", ("nCells",))
            lon[:] = np.linspace(0.1, 0.5, n_cells)
        for name in REQUIRED:
            if name == omit: continue
            dims = ("Time","nCells") if name == "surface_pressure" else ("Time","nCells","nVertLevels")
            ds.createVariable(name, "f4", dims)

def _invariant(tmp_path: Path, shift: float = 0.0) -> Path:
    path = tmp_path / ("invariant-shifted.nc" if shift else "invariant.nc")
    with netCDF4.Dataset(path, "w") as ds:
        ds.createDimension("nVertLevelsP1", 3)
        ds.createDimension("nCells", 3)
        zgrid = ds.createVariable("zgrid", "f8", ("nVertLevelsP1", "nCells"))
        zgrid[:] = np.array([[0.0, 10.0, 20.0], [1000.0, 1010.0, 1020.0], [3000.0, 3010.0, 3020.0]]) + shift
    return path

def _config(mesh: Path):
    return {"mesh":{"name":"x1.test","grid":str(mesh),"nvertlevels":2},"static":{"invariant":str(_invariant(mesh.parent))},"bflow":{"wind_transform":{"zonal_file_variable":"uReconstructZonal","meridional_file_variable":"uReconstructMeridional","template_file_variable":"theta"},"copy_variables":REQUIRED[1:],"derived_variables":[{"inputs":["pressure_p","pressure_base"],"template_file":"pressure_p"},{"theta_file":"theta","template_file":"theta"},{"mixing_ratio_file":"qv","template_file":"qv"}]}}

def _canonical_mesh(tmp_path: Path) -> Path:
    path = tmp_path / "mesh.nc"
    _state(path, "2000-01-01_00:00:00")
    return path

def _manifest(tmp_path: Path, omit=None, mismatch=False, wrong_time=False, shift_mesh=False, coordinates=("latCell", "lonCell")):
    path=tmp_path/"legacy.tsv"
    with path.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.writer(stream,delimiter="\t"); writer.writerow(["valid_time","f048","f024"])
        for i in range(4):
            valid=f"2018-04-{i+1:02d}_00:00:00"; f48=tmp_path/f"f48-{i}.nc"; f24=tmp_path/f"f24-{i}.nc"
            _state(f48,"1999-01-01_00:00:00" if wrong_time and i==0 else valid,omit=omit if i==0 else None,shift_mesh=shift_mesh and i==0,coordinates=coordinates)
            _state(f24,valid,n_cells=4 if mismatch and i==0 else 3,coordinates=coordinates); writer.writerow([valid,f48,f24])
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


def test_rejects_state_with_wrong_case_vertical_level_count(tmp_path):
    manifest = _manifest(tmp_path)
    config = _config(_canonical_mesh(tmp_path))
    config["mesh"]["nvertlevels"] = 3
    with pytest.raises(ManifestError, match="mesh.nvertlevels=3"):
        validate_manifest(manifest, config=config)


def test_reports_vertical_grid_fingerprint(tmp_path):
    report = validate_manifest(
        _manifest(tmp_path),
        config=_config(_canonical_mesh(tmp_path)),
    )
    vertical = report["scientific_contract"]["mesh_identity"]["vertical_identity"]
    assert vertical["variable"] == "zgrid"
    assert vertical["interface_count"] == 3
    assert len(vertical["zgrid_sha256"]) == 64
    assert report["scientific_contract"]["pairs"][0]["f048"]["vertical_grid_proof"] == "case-invariant-plus-level-count"


def test_rejects_invariant_with_wrong_vertical_interface_count(tmp_path):
    config = _config(_canonical_mesh(tmp_path))
    config["mesh"]["nvertlevels"] = 3
    with pytest.raises(ManifestError, match="zgrid has 3 interfaces"):
        validate_manifest(_manifest(tmp_path), config=config)


def test_accepts_native_da_state_without_coordinates_and_reports_limited_proof(tmp_path):
    # The pinned MPAS immutable da_state publishes atmospheric fields, not mesh coordinates.
    report = validate_manifest(
        _manifest(tmp_path, coordinates=()),
        config=_config(_canonical_mesh(tmp_path)),
    )
    for pair in report["scientific_contract"]["pairs"]:
        for lead in ("f048", "f024"):
            mesh = pair[lead]["mesh"]
            assert mesh["state_proof"] == "case-grid-plus-cell-count"
            assert mesh["state_geometry_verified"] is False
            assert mesh["nCells"] == 3
    assert report["scientific_contract"]["mesh_identity"]["state_geometry_verified"] is False


def test_reports_direct_geometry_proof_when_coordinates_are_present(tmp_path):
    report = validate_manifest(_manifest(tmp_path), config=_config(_canonical_mesh(tmp_path)))
    mesh = report["scientific_contract"]["pairs"][0]["f048"]["mesh"]
    assert mesh["state_proof"] == "state-coordinates-match-case-grid"
    assert mesh["state_geometry_verified"] is True
    assert report["scientific_contract"]["mesh_identity"]["state_geometry_verified"] is True


def test_rejects_native_state_with_wrong_canonical_cell_count(tmp_path):
    with pytest.raises(ManifestError, match="canonical mesh.*nCells"):
        validate_manifest(
            _manifest(tmp_path, coordinates=(), mismatch=True),
            config=_config(_canonical_mesh(tmp_path)),
        )


@pytest.mark.parametrize("coordinates", [("latCell",), ("lonCell",)])
def test_rejects_partial_state_coordinates(tmp_path, coordinates):
    with pytest.raises(ManifestError, match="incomplete.*coordinates"):
        validate_manifest(
            _manifest(tmp_path, coordinates=coordinates),
            config=_config(_canonical_mesh(tmp_path)),
        )


def test_canonical_grid_still_requires_coordinates_for_native_states(tmp_path):
    mesh = tmp_path / "mesh.nc"
    _state(mesh, "2000-01-01_00:00:00", coordinates=())
    with pytest.raises(ManifestError, match="MPAS mesh identity source.*missing latCell"):
        validate_manifest(_manifest(tmp_path, coordinates=()), config=_config(mesh))


def test_mixed_campaign_does_not_claim_all_state_geometries_verified(tmp_path):
    manifest = _manifest(tmp_path)
    _state(tmp_path / "f48-0.nc", "2018-04-01_00:00:00", coordinates=())
    report = validate_manifest(manifest, config=_config(_canonical_mesh(tmp_path)))
    contract = report["scientific_contract"]
    assert contract["mesh_identity"]["state_geometry_verified"] is False
    assert contract["pairs"][0]["f048"]["mesh"]["state_geometry_verified"] is False
    assert contract["pairs"][0]["f024"]["mesh"]["state_geometry_verified"] is True
