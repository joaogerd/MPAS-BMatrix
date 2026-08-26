from __future__ import annotations

import yaml

import bmatrix.onboarding as onboarding
from bmatrix.cli import build_parser, main
from bmatrix.onboarding import (
    discover_runtime,
    doctor_checks,
    load_resource_catalog,
    load_site_profile,
    save_setup,
)


def test_public_cli_exposes_onboarding_commands():
    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if getattr(action, "choices", None)
    )
    assert {"setup", "doctor", "paths", "check-config"}.issubset(subparsers.choices)


def test_site_profile_and_resource_catalog_are_logical_contracts():
    profile, profile_path = load_site_profile("jaci")
    catalog, catalog_path = load_resource_catalog("x1.10242")

    assert profile_path.name == "jaci.yaml"
    assert profile["resources"]["default"] == "x1.10242"
    assert "compatibility_candidates" in profile["runtime"]["monan_jedi_install"]

    assert catalog_path.name == "x1.10242.yaml"
    assert catalog["resource"]["nCells"] == 10242
    assert catalog["resource"]["nVertLevels"] == 55
    assert catalog["mesh"]["grid"].endswith("x1.10242.grid.nc")


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

    discovery = discover_runtime(site="generic")
    resolved = {item.name: item for item in discovery.values}

    for name, path in overrides.items():
        assert resolved[name].value == str(path)
        assert resolved[name].source == "environment"


def test_saved_setup_override_supports_nonstandard_layout(monkeypatch, tmp_path):
    config_path = tmp_path / "setup.yaml"
    workspace = tmp_path / "workspace"
    install = tmp_path / "custom-monan-jedi"
    workspace.mkdir()
    install.mkdir()
    monkeypatch.setattr(onboarding, "USER_CONFIG", config_path)
    monkeypatch.delenv("MONAN_JEDI_INSTALL", raising=False)

    save_setup(
        site="generic",
        workspace=workspace,
        overrides={"MONAN_JEDI_INSTALL": install},
        path=config_path,
    )
    discovery = discover_runtime(site="generic")
    resolved = {item.name: item for item in discovery.values}

    assert resolved["MONAN_JEDI_INSTALL"].value == str(install)
    assert resolved["MONAN_JEDI_INSTALL"].source == "user-config"


def test_workspace_argument_wins_during_setup_discovery(monkeypatch, tmp_path):
    shell_workspace = tmp_path / "shell-work"
    requested_workspace = tmp_path / "requested-work"
    monkeypatch.setenv("WORK_ROOT", str(shell_workspace))

    discovery = discover_runtime(site="generic", workspace=requested_workspace)
    resolved = {item.name: item for item in discovery.values}

    assert resolved["WORK_ROOT"].value == str(requested_workspace)
    assert resolved["WORK_ROOT"].source == "argument"


def test_jaci_discovery_prefers_current_monan_jedi_install_name(monkeypatch):
    calls = []
    monkeypatch.setattr(onboarding, "_prefix_from_command", lambda _command: None)
    monkeypatch.setattr(onboarding, "_latest_glob", lambda _pattern: None)

    def capture_candidates(candidates):
        values = tuple(candidates)
        calls.append(values)
        return None

    monkeypatch.setattr(onboarding, "_first_existing", capture_candidates)

    onboarding.discover_runtime(site="jaci")

    install_candidates = calls[0]
    assert install_candidates[0].name == "monan-jedi"
    assert install_candidates[1].name == "monan-jedi-mpas"


def test_paths_reports_partial_discovery_without_loading_config(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    for name in (
        "MONAN_JEDI_INSTALL",
        "MPAS_MESH_ROOT",
        "MPAS_JEDI_STATIC_ROOT",
        "MONAN_JEDI_SOURCE",
        "STACK_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)

    status = main(["paths", "--site", "generic"])
    output = capsys.readouterr().out

    assert status == 1
    assert "MPAS-BMatrix path resolution" in output
    assert "<unresolved>" in output
    assert "Configuration-specific file paths cannot be fully expanded yet." in output


def test_save_setup_persists_semantic_choices_and_no_implicit_paths(tmp_path):
    config_path = tmp_path / "setup.yaml"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    saved = save_setup(site="jaci", workspace=workspace, path=config_path)
    payload = yaml.safe_load(saved.read_text(encoding="utf-8"))

    assert payload == {
        "site": "jaci",
        "workspace": str(workspace.resolve()),
        "resource": "x1.10242",
    }


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
