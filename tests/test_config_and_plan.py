from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bmatrix.config import deep_merge, load_config
from bmatrix.errors import ConfigurationError
from bmatrix.pipeline import BuildRequest, plan


def test_deep_merge_preserves_nested_contract_settings() -> None:
    merged = deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"b": 3}})
    assert merged == {"a": {"b": 3, "c": 2}}


def test_deep_merge_replaces_scientific_lists_atomically() -> None:
    merged = deep_merge({"controls": ["a", "b"]}, {"controls": ["c"]})
    assert merged == {"controls": ["c"]}


def test_load_config_composes_site_case_and_stage_fragments(tmp_path: Path) -> None:
    (tmp_path / "site.yaml").write_text(
        yaml.safe_dump(
            {
                "project": {"project_root": "/repo", "work_root": "/work"},
                "environment": {"loader": "scripts/load.sh"},
                "install": {"root": "/install"},
                "pbs": {"queues": {"bmatrix": "queue"}},
            }
        )
    )
    fragments = tmp_path / "scientific"
    fragments.mkdir()
    (fragments / "controls.yaml").write_text(
        yaml.safe_dump(
            {
                "controls": [
                    {"code": "air_temperature", "file": "temperature", "dimensions": "3d"}
                ]
            }
        )
    )
    (fragments / "bflow.yaml").write_text(
        yaml.safe_dump(
            {
                "bflow": {
                    "nmc": {"older_lead_hours": 48, "newer_lead_hours": 24},
                    "products": {
                        "template": "template_PTB.nc",
                        "older_full": "FULL_f48.nc",
                        "newer_full": "FULL_f24.nc",
                        "perturbation": "PTB_f48mf24.nc",
                    },
                    "regridding": {
                        "resolution_deg": 1.0,
                        "lower_left": [-89.5, -179.5],
                        "upper_right": [89.5, 179.5],
                    },
                    "wind_transform": {"outputs": {}},
                }
            }
        )
    )
    (tmp_path / "contract.yaml").write_text(
        yaml.safe_dump(
            {
                "include": [
                    "scientific/controls.yaml",
                    "scientific/bflow.yaml",
                ],
                "schema_version": 2,
            }
        )
    )
    case = tmp_path / "case.yaml"
    case.write_text(
        yaml.safe_dump(
            {
                "include": "site.yaml",
                "mesh": {"name": "x1.test", "grid": "/mesh.nc", "nproc": 4},
                "runtime": {"config_dt": 60},
                "bmatrix": {"configuration": "contract.yaml"},
            }
        )
    )

    config = load_config(case)

    assert config["project"]["work_root"] == "/work"
    assert config["mesh"]["name"] == "x1.test"
    assert config["schema_version"] == 2
    assert config["controls"][0]["file"] == "temperature"
    assert config["bflow"]["products"]["perturbation"] == "PTB_f48mf24.nc"
    assert [Path(item).name for item in config["configuration_sources"]] == ["site.yaml", "case.yaml"]
    assert [Path(item).name for item in config["bmatrix_contract_sources"]] == [
        "controls.yaml",
        "bflow.yaml",
        "contract.yaml",
    ]


def test_load_config_rejects_include_cycles(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text("include: b.yaml\n")
    (tmp_path / "b.yaml").write_text("include: a.yaml\n")

    with pytest.raises(ConfigurationError, match="Ciclo de include"):
        load_config(tmp_path / "a.yaml")


def test_repository_default_config_composes_all_scientific_stages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = Path(__file__).resolve().parents[1]
    variables = {
        "BMATRIX_ROOT": str(root),
        "WORK_ROOT": str(tmp_path / "work"),
        "MONAN_JEDI_INSTALL": str(tmp_path / "install"),
        "MONAN_JEDI_UNBALANCE_EXE": str(tmp_path / "unbalance.x"),
        "MPAS_MESH_ROOT": str(tmp_path / "meshes"),
        "MPAS_JEDI_STATIC_ROOT": str(tmp_path / "static"),
        "MONAN_JEDI_SOURCE": str(tmp_path / "MONAN-JEDI"),
    }
    for name, value in variables.items():
        monkeypatch.setenv(name, value)

    config = load_config(root / "configs" / "jaci-x1.10242.yaml")

    assert config["project"]["name"] == "MPAS-BMatrix"
    assert config["mesh"]["name"] == "x1.10242"
    assert config["schema_version"] == 2
    for section in (
        "controls",
        "bflow",
        "vbal",
        "unbalance",
        "hdiag",
        "nicas",
        "single_observation",
        "dirac",
    ):
        assert section in config
    assert "wps" not in config
    assert config["install"]["unbalance_executable"] == variables["MONAN_JEDI_UNBALANCE_EXE"]


def test_plan_from_manifest_is_side_effect_free(tmp_path: Path) -> None:
    data = {
        "project": {"work_root": str(tmp_path / "work"), "project_root": str(tmp_path)},
        "mesh": {"name": "x1.test", "grid": str(tmp_path / "mesh.nc"), "nproc": 4},
        "runtime": {"config_dt": 60},
        "bflow": {
            "nmc": {"older_lead_hours": 48, "newer_lead_hours": 24},
            "products": {"template": "template_PTB.nc", "older_full": "FULL_f48.nc", "newer_full": "FULL_f24.nc", "perturbation": "PTB_f48mf24.nc"},
            "regridding": {"resolution_deg": 1.0, "lower_left": [-89.5, -179.5], "upper_right": [89.5, 179.5]},
            "wind_transform": {"outputs": {}},
        },
        "controls": [{"code": "air_temperature", "file": "temperature", "dimensions": "3d"}],
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(data))
    manifest = tmp_path / "manifest.tsv"
    manifest.write_text(
        "valid_time\tf048\tf024\n"
        "2026-06-10_00:00:00\t/a/f048.nc\t/a/f024.nc\n"
    )
    config = load_config(config_path)
    result = plan(config, BuildRequest(manifest=manifest, to_stage="nicas"))
    assert result.stages == ("bflow", "vbal", "unbalance", "hdiag", "nicas")
    assert result.paths.bflow.name.startswith("np4_2026061000")
    assert not result.paths.bflow.exists()


def test_stage_order_includes_unbalance_between_vbal_and_hdiag(tmp_path: Path) -> None:
    data = {
        "project": {"work_root": str(tmp_path / "work"), "project_root": str(tmp_path)},
        "mesh": {"name": "x1.test", "grid": str(tmp_path / "mesh.nc"), "nproc": 4},
        "runtime": {"config_dt": 60},
        "bflow": {
            "nmc": {"older_lead_hours": 48, "newer_lead_hours": 24},
            "products": {"template": "template_PTB.nc", "older_full": "FULL_f48.nc", "newer_full": "FULL_f24.nc", "perturbation": "PTB_f48mf24.nc"},
            "regridding": {"resolution_deg": 1.0, "lower_left": [-89.5, -179.5], "upper_right": [89.5, 179.5]},
            "wind_transform": {"outputs": {}},
        },
        "controls": [{"code": "air_temperature", "file": "temperature", "dimensions": "3d"}],
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(data))
    manifest = tmp_path / "manifest.tsv"
    manifest.write_text(
        "valid_time\tf048\tf024\n"
        "2026-06-10_00:00:00\t/a/f048.nc\t/a/f024.nc\n"
    )

    result = plan(load_config(config_path), BuildRequest(manifest=manifest, from_stage="unbalance", to_stage="hdiag"))

    assert result.stages == ("unbalance", "hdiag")
    assert result.paths.unbalance.parent.name == "unbalance"
    assert result.paths.hdiag.parent.name == "hdiag"
