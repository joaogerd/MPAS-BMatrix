from __future__ import annotations

from pathlib import Path

import yaml

from bmatrix.cli import build_parser
from bmatrix.onboarding import discover_runtime, doctor_checks, save_setup


def test_public_cli_exposes_onboarding_commands():
    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if getattr(action, "choices", None)
    )
    assert {"setup", "doctor", "paths", "check-config"}.issubset(subparsers.choices)


def test_discovery_keeps_explicit_environment_overrides(monkeypatch, tmp_path):
    overrides = {
        "BMATRIX_ROOT": tmp_path / "repo",
        "WORK_ROOT": tmp_path / "work",
        "MONAN_JEDI_INSTALL": tmp_path / "install",
        "MPAS_MESH_ROOT": tmp_path / "meshes",
        "MPAS_JEDI_STATIC_ROOT": tmp_path / "static",
        "MONAN_JEDI_SOURCE": tmp_path / "source",
        "STACK_ROOT": tmp_path / "stack",
    }
    for name, path in overrides.items():
        path.mkdir(parents=True)
        monkeypatch.setenv(name, str(path))

    discovery = discover_runtime(site="generic", workspace=tmp_path / "ignored")
    resolved = {item.name: item for item in discovery.values}

    for name, path in overrides.items():
        assert resolved[name].value == str(path)
        assert resolved[name].source == "environment"


def test_save_setup_persists_only_site_and_workspace(tmp_path):
    config_path = tmp_path / "setup.yaml"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    saved = save_setup(site="jaci", workspace=workspace, path=config_path)
    payload = yaml.safe_load(saved.read_text(encoding="utf-8"))

    assert payload == {"site": "jaci", "workspace": str(workspace.resolve())}


def test_doctor_checks_include_requested_mpi_partition(tmp_path):
    graph = tmp_path / "mesh" / "x1.10242.graph.info"
    partitions = tmp_path / "partitions"
    install = tmp_path / "install"
    config = {
        "project": {"project_root": str(tmp_path / "repo"), "work_root": str(tmp_path / "work")},
        "install": {
            "root": str(install),
            "unbalance_executable": str(install / "bin" / "mpasjedi_unbalance_ensemble.x"),
        },
        "mesh": {
            "grid": str(tmp_path / "mesh" / "x1.10242.grid.nc"),
            "graph": str(graph),
            "partitions_dir": str(partitions),
            "nproc": 128,
        },
        "static": {
            "invariant": str(tmp_path / "static" / "x1.10242.invariant.nc"),
            "tutorial_physics_files": str(tmp_path / "static"),
            "geovars": str(tmp_path / "static" / "geovars.yaml"),
            "keptvars": str(tmp_path / "static" / "keptvars.yaml"),
        },
        "environment": {"variables": {"STACK_ROOT": str(tmp_path / "stack")}},
    }

    checks = doctor_checks(config)
    by_name = {name: path for name, path, _ in checks}

    assert by_name["MPI partition np128"] == partitions / "x1.10242.graph.info.part.128"
    assert by_name["mpasjedi_error_covariance_toolbox.x"] == (
        install / "bin" / "mpasjedi_error_covariance_toolbox.x"
    )
