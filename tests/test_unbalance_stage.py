from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bmatrix.artifacts import StageManifest, write_manifest
from bmatrix.hdiag_core.prepare import prepare as prepare_hdiag
from bmatrix.unbalance_core.checks import validate_unbalanced_samples
from bmatrix.unbalance_core.config_files import write_unbalance_yaml
from bmatrix.unbalance_core.model import unbalance_exe


def _config(tmp_path: Path) -> dict[str, object]:
    return {
        "project": {"work_root": str(tmp_path / "work"), "project_root": str(tmp_path)},
        "mesh": {"name": "x1.test", "grid": str(tmp_path / "mesh.nc"), "nproc": 128},
        "install": {"root": str(tmp_path / "install")},
        "bflow": {"products": {"perturbation": "PTB_f48mf24.nc"}},
        "controls": [
            {"code": "psi", "file": "stream_function"},
            {"code": "chi", "file": "velocity_potential"},
            {"code": "t", "file": "temperature"},
            {"code": "q", "file": "spechum"},
            {"code": "ps", "file": "surface_pressure"},
        ],
        "vbal": {
            "files_prefix": "mpas",
            "group_variable_order": ["psi", "chi", "t", "q", "ps"],
            "relations": [
                {"balanced_variable": "chi", "unbalanced_variable": "psi", "diagonal_regression": True},
                {"balanced_variable": "t", "unbalanced_variable": "psi"},
                {"balanced_variable": "ps", "unbalanced_variable": "psi"},
            ],
            "pseudo_inverse": True,
            "dominant_mode": 20,
        },
    }


def test_unbalance_yaml_uses_ensemble_and_vertical_balance_only(tmp_path: Path) -> None:
    output = tmp_path / "run_unbalance.yaml"

    write_unbalance_yaml(_config(tmp_path), output, nmembers=4, date="2026-06-22T00:00:00Z")

    rendered = yaml.safe_load(output.read_text())
    assert "ensemble" in rendered
    assert "ensemble pert" not in rendered
    assert rendered["ensemble"]["members from template"]["template"]["filename"] == "../samples/PTB_f48mf24_%mem%.nc"
    assert rendered["ensemble"]["members from template"]["template"]["transform model to analysis"] is False
    assert rendered["output"]["filename"] == "../samplesUnbalanced/PTB_f48mf24_%{member}%.nc"
    block = rendered["inverse blocks"][0]
    assert block["saber block name"] == "BUMP_VerticalBalance"
    assert block["read"]["drivers"] == {
        "read local sampling": True,
        "read global sampling": False,
        "read vertical balance": True,
    }
    assert "BUMP_NICAS" not in output.read_text()
    assert "StdDev" not in output.read_text()


def test_unbalance_executable_prefers_explicit_platform_value(tmp_path: Path) -> None:
    platform = tmp_path / "platform-unbalance.x"
    legacy = tmp_path / "legacy-unbalance.x"
    platform.write_text("")
    legacy.write_text("")

    config = {
        "install": {
            "root": str(tmp_path / "install"),
            "unbalance_executable": str(platform),
        },
        "unbalance": {"executable": str(legacy)},
    }

    assert unbalance_exe(config) == platform


def test_unbalance_executable_keeps_legacy_explicit_value_before_default(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy-unbalance.x"
    legacy.write_text("")

    config = {
        "install": {"root": str(tmp_path / "install")},
        "unbalance": {"executable": str(legacy)},
    }

    assert unbalance_exe(config) == legacy


def _write_unbalance_manifest(workspace: Path) -> None:
    write_manifest(
        StageManifest(
            stage="unbalance",
            workspace=str(workspace),
            inputs={"vbal_workspace": str(workspace / "vbal-source")},
            outputs={"samples_unbalanced": str(workspace / "samplesUnbalanced")},
            metadata={"sample_stem": "PTB_f48mf24", "members": 4, "date": "2026-06-22T00:00:00Z"},
            status="prepared",
        )
    )


def test_unbalance_validation_rejects_incomplete_set(tmp_path: Path) -> None:
    _write_unbalance_manifest(tmp_path)
    samples = tmp_path / "samplesUnbalanced"
    samples.mkdir()
    for index in range(1, 4):
        (samples / f"PTB_f48mf24_{index:03d}.nc").write_bytes(b"x")

    errors = validate_unbalanced_samples(tmp_path, required_variables=["temperature"], expected_members=4)

    assert errors
    assert "esperadas" in errors[0]


def test_unbalance_validation_rejects_non_cdf5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_unbalance_manifest(tmp_path)
    samples = tmp_path / "samplesUnbalanced"
    samples.mkdir()
    for index in range(1, 5):
        (samples / f"PTB_f48mf24_{index:03d}.nc").write_bytes(b"x")
    monkeypatch.setattr("bmatrix.unbalance_core.checks._ncdump_kind", lambda path: "netCDF-4")

    errors = validate_unbalanced_samples(tmp_path, required_variables=["temperature"], expected_members=4)

    assert len(errors) == 4
    assert all("esperado cdf5" in error for error in errors)


def test_hdiag_prepare_requires_valid_vbal_manifest(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="Manifesto"):
        prepare_hdiag(_config(tmp_path), tmp_path / "missing-vbal", workspace=tmp_path / "hdiag")
