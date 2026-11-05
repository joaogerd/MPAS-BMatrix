"""Scientific safety cases that must not inherit original tutorial constants."""

from pathlib import Path

import pytest
import yaml

from bmatrix.errors import ConfigurationError
from bmatrix.config import validate_config_shape
from bmatrix.pipeline import BuildRequest, _pairs_from_request
from bmatrix.scheduler import configured_mpi_ranks
from bmatrix.scientific_config import vbal_dominant_mode
from bmatrix.nicas_core.config_files import write_nicas_yaml


def _case(tmp_path: Path) -> dict:
    return {
        "project": {"work_root": str(tmp_path)},
        "mesh": {"name": "regional.mesh", "nproc": 96, "nvertlevels": 12},
        "runtime": {},
        "bflow": {
            "forecast_state_template": "runs/{mesh_name}/{init_compact}/f{lead_padded}/state_dt{dt}.nc",
            "nmc": {"older_lead_hours": 48, "newer_lead_hours": 24},
            "products": {"perturbation": "PTB.nc"},
        },
        "vbal": {"dominant_mode": 8},
        "nicas": {"dirac_points": []},
    }


def test_range_requires_actual_timestep_not_240km_default(tmp_path: Path):
    config = _case(tmp_path)
    request = BuildRequest(
        start_valid_time="2027-01-01_00:00:00",
        end_valid_time="2027-01-02_00:00:00",
        valid_interval_hours=12,
    )
    with pytest.raises(ConfigurationError, match="timestep"):
        _pairs_from_request(config, request)
    pairs, _ = _pairs_from_request(
        config,
        BuildRequest(
            start_valid_time=request.start_valid_time,
            end_valid_time=request.end_valid_time,
            valid_interval_hours=12,
            dt=135,
        ),
    )
    assert len(pairs) == 3
    assert all("state_dt135.nc" in str(pair.f048) for pair in pairs)


def test_manifest_rejects_lead_definitions_that_disagree_with_f048_f024(tmp_path: Path):
    config = _case(tmp_path)
    manifest = tmp_path / "pairs.tsv"
    manifest.write_text(
        "valid_time\tf048_state\tf024_state\n"
        "2027-01-01_00:00:00\t/older/state.nc\t/newer/state.nc\n"
    )
    config["bflow"]["nmc"]["older_lead_hours"] = 72
    with pytest.raises(ConfigurationError, match="outro par"):
        _pairs_from_request(config, BuildRequest(manifest=manifest))


def test_mpi_count_must_be_selected_explicitly(tmp_path: Path):
    config = _case(tmp_path)
    assert configured_mpi_ranks(config) == 96
    del config["mesh"]["nproc"]
    with pytest.raises(ValueError, match="mesh.nproc"):
        configured_mpi_ranks(config)


def test_vbal_modes_are_valid_for_selected_vertical_grid(tmp_path: Path):
    config = _case(tmp_path)
    assert vbal_dominant_mode(config) == 8
    config["vbal"]["dominant_mode"] = 20
    with pytest.raises(ConfigurationError, match="vbal.dominant_mode"):
        vbal_dominant_mode(config)
    config["vbal"].pop("dominant_mode")
    with pytest.raises(ConfigurationError, match="vbal.dominant_mode"):
        vbal_dominant_mode(config)


def test_nicas_impulse_requires_real_level_choice(tmp_path: Path):
    config = _case(tmp_path)
    config["nicas"]["dirac_points"] = [
        {"longitude": -50.0, "latitude": -20.0, "variable": "surface_pressure"},
    ]
    with pytest.raises(ValueError, match="dirac_level_from_top"):
        write_nicas_yaml(config, tmp_path / "nicas.yaml", "surface_pressure",
                         "2027-01-01T00:00:00Z", 12)
    config["nicas"]["dirac_level_from_top"] = 20
    with pytest.raises(ValueError, match="dirac_level_from_top"):
        write_nicas_yaml(config, tmp_path / "nicas.yaml", "surface_pressure",
                         "2027-01-01T00:00:00Z", 12)


def test_nicas_2d_level_comes_from_controls_not_variable_name(tmp_path: Path):
    config = _case(tmp_path)
    config["controls"] = [
        {"code": "soil", "file": "custom_soil", "dimensions": "2d"},
        {"code": "thermal", "file": "temperature", "dimensions": "3d"},
    ]
    config["nicas"] = {
        "dirac_level_from_top": 4,
        "dirac_points": [
            {"longitude": -55.0, "latitude": -12.0, "variable": "soil"},
            {"longitude": -55.0, "latitude": -12.0, "variable": "thermal"},
        ],
    }
    for variable, expected in (("custom_soil", 1), ("temperature", 9)):
        filename = tmp_path / f"{variable}.yaml"
        write_nicas_yaml(config, filename, variable, "2027-01-01T00:00:00Z", 12)
        payload = yaml.safe_load(filename.read_text())
        points = payload["background error"]["saber central block"]["calibration"]["dirac"]
        assert len(points) == 1
        assert points[0]["level"] == expected


def test_nondefault_covariance_output_prefix_is_rejected_until_pipeline_is_generic(tmp_path: Path):
    config = _case(tmp_path)
    config["mesh"]["grid"] = "mesh.nc"
    config["bflow"]["regridding"] = {}
    config["bflow"]["wind_transform"] = {}
    config["vbal"]["files_prefix"] = "regional"
    with pytest.raises(ConfigurationError, match="files_prefix"):
        validate_config_shape(config)


def test_date_range_without_source_template_fails_without_guessing(tmp_path: Path):
    config = _case(tmp_path)
    config['bflow'].pop('forecast_state_template')
    request = BuildRequest(start_valid_time='2027-01-01_00:00:00',
                           end_valid_time='2027-01-02_00:00:00', dt=135)
    with pytest.raises(ConfigurationError, match='forecast_state_template'):
        _pairs_from_request(config, request)


def test_same_case_and_window_are_isolated_by_manifest_content(tmp_path: Path):
    config = _case(tmp_path)
    a = tmp_path / 'a.tsv'
    b = tmp_path / 'b.tsv'
    heading = 'valid_time\tf048_state\tf024_state\n'
    a.write_text(heading + '2027-01-01_00:00:00\t/old/a.nc\t/new/a.nc\n'
                 + '2027-01-02_00:00:00\t/old/b.nc\t/new/b.nc\n')
    b.write_text(heading + '2027-01-01_00:00:00\t/old/a.nc\t/new/a.nc\n'
                 + '2027-01-02_00:00:00\t/old/c.nc\t/new/c.nc\n')
    _, first = _pairs_from_request(config, BuildRequest(manifest=a))
    _, second = _pairs_from_request(config, BuildRequest(manifest=b))
    assert first != second
    assert first.name.startswith('np96_2027010100_2027010200_mesh-regional.mesh')
    assert '_source-' in first.name
    assert not first.exists() and not second.exists()
