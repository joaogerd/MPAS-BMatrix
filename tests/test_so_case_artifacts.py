"""SO regression tests use each generated case's real observation contract."""
from pathlib import Path

import pytest
import yaml

from bmatrix.bflow_core.netcdf_utils import CDF5_FORMAT
from bmatrix.so_core.checks import (
    expected_observation_files, expected_analysis_fields, so_errors,
)
from bmatrix.so_core.jobs import clean_outputs
from bmatrix.artifacts import StageManifest, write_manifest


def _case(tmp_path: Path, filename: str = "case_temperature.h5") -> None:
    payload = {
        "observations": {
            "observers": [
                {"obs space": {"obsdataout": {"engine": {"obsfile": f"./{filename}"}}}}
            ]
        }
    }
    (tmp_path / "run_SO.yaml").write_text(yaml.safe_dump(payload))
    (tmp_path / "run_SO.runlog").write_text(
        "CostFunction::addIncrement: Analysis:\nFinishing with status = 0\n"
    )
    (tmp_path / "stdout.log").write_text("")
    (tmp_path / "stderr.log").write_text("")


def _analysis(tmp_path: Path, variables=("theta",)) -> None:
    netcdf4 = pytest.importorskip("netCDF4")
    with netcdf4.Dataset(tmp_path / "an.2027-01-01_00.00.00.nc", "w", format=CDF5_FORMAT) as ds:
        ds.createDimension("Time", 1)
        ds.createDimension("nCells", 3)
        for name in variables:
            ds.createVariable(name, "f4", ("Time", "nCells"))[:] = 1.0


def test_so_uses_generated_observer_files_instead_of_builtin_t_u(tmp_path: Path):
    _case(tmp_path)
    _analysis(tmp_path)
    write_manifest(StageManifest(
        stage="so", workspace=str(tmp_path),
        metadata={"required_native_analysis_fields": ["theta"]}
    ))
    (tmp_path / "case_temperature.h5").write_text("present")
    assert expected_observation_files(tmp_path) == ["case_temperature.h5"]
    assert expected_analysis_fields(tmp_path) == ["theta"]
    assert so_errors(tmp_path) == []
    (tmp_path / "case_temperature.h5").unlink()
    assert any("case_temperature.h5" in problem for problem in so_errors(tmp_path))
    assert not any("obsout_SO_T" in problem for problem in so_errors(tmp_path))


def test_so_clean_only_selected_observation_products(tmp_path: Path):
    _case(tmp_path, "custom_airtemp.h5")
    (tmp_path / "custom_airtemp.h5").write_text("previous result")
    (tmp_path / "unrelated_science.h5").write_text("must survive")
    clean_outputs(tmp_path)
    assert not (tmp_path / "custom_airtemp.h5").exists()
    assert (tmp_path / "unrelated_science.h5").is_file()


def test_invalid_generated_observation_file_does_not_fall_back_silently(tmp_path: Path):
    _case(tmp_path, "../other-case/accidental.h5")
    with pytest.raises(ValueError, match="diretório de execução"):
        expected_observation_files(tmp_path)
