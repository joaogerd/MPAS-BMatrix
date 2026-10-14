from pathlib import Path

import pytest

from bmatrix.vbal_core.static import link_static_files


def test_vbal_stages_explicit_15km_geometry_without_tutorial(tmp_path):
    source = tmp_path / "inputs"
    source.mkdir()
    run = tmp_path / "run"
    run.mkdir()
    for name in (
        "x1.2621442.graph.info",
        "x1.2621442.graph.info.part.480",
        "x1.2621442.invariant.nc",
        "bg.nc",
        "template.nc",
    ):
        (source / name).write_text("data")
    (source / "custom.nml").write_text(
        "config_start_time = '2000-01-01_00:00:00'\n"
        "config_block_decomp_file_prefix = 'old.graph.info.part.'\n"
    )
    (source / "custom.xml").write_text(
        '<streams><immutable_stream name="invariant" '
        'filename_template="old.invariant.nc" /></streams>'
    )
    config = {
        "mesh": {
            "name": "x1.2621442",
            "graph": str(source / "x1.2621442.graph.info"),
            "partitions_dir": str(source),
            "nproc": 480,
        },
        "static": {
            "invariant": str(source / "x1.2621442.invariant.nc"),
            "namelist": str(source / "custom.nml"),
            "streams": str(source / "custom.xml"),
            "support_dir": str(source),
        },
        "controls": [{"code": "T", "file": "air_temperature"}],
    }
    link_static_files(config, run, source / "bg.nc", source / "template.nc", "2026-06-22_00:00:00")
    assert "x1.2621442.graph.info.part." in (run / "namelist.atmosphere").read_text()
    assert "2026-06-22_00:00:00" in (run / "namelist.atmosphere").read_text()
    assert "x1.2621442.invariant.nc" in (run / "streams.atmosphere").read_text()
    assert (run / "x1.2621442.graph.info.part.480").is_file()


def test_new_mesh_rejects_implicit_240km_geometry(tmp_path):
    graph = tmp_path / "x1.2621442.graph.info"
    graph.touch()
    (tmp_path / "x1.2621442.graph.info.part.480").touch()
    (tmp_path / "namelist.atmosphere_240km").write_text("config_start_time = 'old'")
    config = {
        "mesh": {
            "name": "x1.2621442",
            "graph": str(graph),
            "partitions_dir": str(tmp_path),
            "nproc": 480,
        },
        "static": {
            "invariant": str(tmp_path / "invariant.nc"),
            "tutorial_physics_files": str(tmp_path),
        },
    }
    (tmp_path / "invariant.nc").touch()
    (tmp_path / "bg.nc").touch()
    (tmp_path / "template.nc").touch()
    run = tmp_path / "run"
    run.mkdir()
    with pytest.raises(ValueError, match="static.namelist"):
        link_static_files(
            config, run, tmp_path / "bg.nc", tmp_path / "template.nc", "2026-06-22_00:00:00"
        )
