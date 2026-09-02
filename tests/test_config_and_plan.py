from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bmatrix.config import deep_merge, expand_env, load_config
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


def test_load_config_rejects_unresolved_environment_variables(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "project": {
                    "project_root": "${MISSING_PROJECT_ROOT}",
                    "work_root": str(tmp_path / "work"),
                },
                "mesh": {"name": "x1.test", "grid": str(tmp_path / "mesh.nc")},
                "runtime": {"config_dt": 60},
                "bflow": {
                    "nmc": {"older_lead_hours": 48, "newer_lead_hours": 24},
                    "products": {},
                    "regridding": {},
                    "wind_transform": {},
                },
            }
        )
    )

    with pytest.raises(ConfigurationError, match="MISSING_PROJECT_ROOT"):
        load_config(config_path)


def test_legacy_install_variable_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MONAN_JEDI_INSTALL_ROOT", raising=False)
    monkeypatch.setenv("MONAN_JEDI_INSTALL", "/legacy/install")
    assert expand_env("${MONAN_JEDI_INSTALL_ROOT}/bin/tool.x") == "/legacy/install/bin/tool.x"


def test_repository_default_config_composes_all_scientific_stages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("USER", "runtime-user")
    monan_jedi_root = str(tmp_path / "install")
    monkeypatch.setenv("MONAN_JEDI_INSTALL_ROOT", monan_jedi_root)

    config = load_config(root / "configs" / "jaci-x1.10242.yaml")

    assert config["project"]["name"] == "MPAS-BMatrix"
    assert config["project"]["project_root"] == "/p/projetos/monan_das/runtime-user/projects/MPAS-BMatrix"
    assert config["project"]["work_root"] == "/p/projetos/monan_das/runtime-user/work/MPAS-BMatrix"
    assert config["mesh"]["name"] == "x1.10242"
    assert config["mesh"]["grid"] == "/p/projetos/monan_das/runtime-user/projects/mpas_meshes/quasi_uniform/x1.10242_240km/mesh/x1.10242.grid.nc"
    assert config["static"]["invariant"] == "/p/projetos/monan_das/runtime-user/external-inputs/mpasjedi_tutorial202509NCAR/MPAS_namelist_stream_physics_files/x1.10242.invariant.nc"
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
    assert config["install"]["root"] == monan_jedi_root
    assert config["install"]["atmosphere_share"] == str(
        Path(monan_jedi_root) / "share/MPAS/core_atmosphere"
    )
    assert config["static"]["geovars"] == str(
        Path(monan_jedi_root)
        / "share/monan-jedi/mpas-jedi/namelists/geovars.yaml"
    )
    assert config["static"]["keptvars"] == str(
        Path(monan_jedi_root)
        / "share/monan-jedi/mpas-jedi/namelists/keptvars.yaml"
    )
    assert config["environment"]["variables"]["STACK_ROOT"] == (
        "/p/projetos/monan_das/runtime-user/work/"
        "spack-stack-inpe-overlay-20260515T181917Z/spack-stack"
    )


def _minimal_pipeline_config(tmp_path: Path) -> Path:
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
    return config_path


def _minimal_manifest(tmp_path: Path) -> Path:
    manifest = tmp_path / "manifest.tsv"
    manifest.write_text(
        "valid_time\tf048\tf024\n"
        "2026-06-10_00:00:00\t/a/f048.nc\t/a/f024.nc\n"
    )
    return manifest


def test_plan_from_manifest_is_side_effect_free(tmp_path: Path) -> None:
    config = load_config(_minimal_pipeline_config(tmp_path))
    result = plan(config, BuildRequest(manifest=_minimal_manifest(tmp_path), to_stage="nicas"))
    assert result.stages == ("bflow", "vbal", "hdiag", "nicas")
    assert result.paths.bflow.name.startswith("np4_2026061000")
    assert not result.paths.bflow.exists()


def test_stage_order_runs_directly_from_vbal_to_hdiag(tmp_path: Path) -> None:
    result = plan(
        load_config(_minimal_pipeline_config(tmp_path)),
        BuildRequest(
            manifest=_minimal_manifest(tmp_path),
            from_stage="vbal",
            to_stage="hdiag",
        ),
    )

    assert result.stages == ("vbal", "hdiag")
    assert not hasattr(result.paths, "unbalance")
    assert result.paths.hdiag.parent.name == "hdiag"
