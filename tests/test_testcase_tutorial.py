"""Regression tests for the reusable tutorial/BMatrix scientific case."""

from copy import deepcopy
from pathlib import Path

import pytest

from bmatrix.bflow_core.model import default_workspace, iter_valid_times
from bmatrix.cli import build_parser, _plot_level
from bmatrix.config import load_config


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "testcase/tutorial-240km"


def test_tutorial_case_preserves_original_science_and_explicit_inputs(monkeypatch):
    monkeypatch.setenv("USER", "ci-user")
    monkeypatch.setenv("MONAN_JEDI_INSTALL_ROOT", "/ci/monan-jedi")
    monkeypatch.setenv("STACK_ROOT", "/ci/spack-stack")
    original = load_config(ROOT / "configs/jaci-x1.10242.yaml")
    archived = load_config(CASE / "jaci.yaml")
    assert archived["bmatrix_contract"] == original["bmatrix_contract"]
    assert archived["mesh"] == original["mesh"]
    assert archived["runtime"] == original["runtime"]
    assert archived["static"]["invariant"] == original["static"]["invariant"]
    assert archived["static"]["namelist"].endswith("namelist.atmosphere_240km")
    assert archived["static"]["streams"].endswith("streams.atmosphere_240km")
    assert archived["static"]["support_dir"].endswith("MPAS_namelist_stream_physics_files")
    assert "tutorial_physics_files" not in archived["static"]
    for fragment in ("controls", "bflow", "vbal", "unbalance", "hdiag", "nicas",
                     "single_observation", "dirac"):
        assert fragment in archived
    sources = archived["bmatrix_contract_sources"]
    assert len(sources) == 9
    assert all(str(CASE) in source for source in sources)


def test_case_can_be_changed_without_any_implicit_tutorial_defaults(monkeypatch):
    monkeypatch.setenv("USER", "ci-user")
    monkeypatch.setenv("MONAN_JEDI_INSTALL_ROOT", "/ci/monan-jedi")
    monkeypatch.setenv("STACK_ROOT", "/ci/spack-stack")
    config = deepcopy(load_config(CASE / "jaci.yaml"))
    config["mesh"]["name"] = "x1.163842"
    config["mesh"]["nproc"] = 192
    config["mesh"]["nvertlevels"] = 70
    config["project"]["case_id"] = "60km-jan2027"
    dates = list(iter_valid_times(
        "2027-01-01_00:00:00", "2027-01-02_00:00:00", 12
    ))
    assert len(dates) == 3
    workspace = default_workspace(config, dates[0], dates[-1])
    assert workspace.name.endswith("_case-60km-jan2027")
    assert "_np" not in workspace.name
    assert workspace.name.startswith("np192_")
    assert _plot_level(config, None) == 34


def test_workspace_id_always_distinguishes_different_meshes():
    def config(mesh):
        return {
            "mesh": {"name": mesh, "nproc": 64},
            "project": {"work_root": "/tmp/work"},
        }

    start = "2027-01-01_00:00:00"
    end = "2027-01-02_00:00:00"
    first = default_workspace(config("x1.163842"), start, end)
    second = default_workspace(config("x1.10242"), start, end)
    assert first != second


def test_cli_requires_case_and_can_output_machine_json():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["check-config"])
    args = parser.parse_args([
        "check-config", "--config", str(CASE / "jaci.yaml"), "--json"
    ])
    assert args.json is True
    assert args.config.endswith("jaci.yaml")
