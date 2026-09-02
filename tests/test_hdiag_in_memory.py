from __future__ import annotations

import importlib
import json
from pathlib import Path

import yaml

from bmatrix.artifacts import StageManifest, write_manifest


def _config(tmp_path: Path) -> dict[str, object]:
    return {
        "project": {"work_root": str(tmp_path / "work")},
        "mesh": {"name": "x1.test", "nproc": 4},
        "bflow": {"products": {"perturbation": "PTB_f48mf24.nc"}},
        "controls": [
            {"code": "psi", "file": "stream_function", "dimensions": "3d"},
            {"code": "chi", "file": "velocity_potential", "dimensions": "3d"},
            {"code": "t", "file": "temperature", "dimensions": "3d"},
            {"code": "q", "file": "spechum", "dimensions": "3d"},
            {"code": "ps", "file": "surface_pressure", "dimensions": "2d"},
        ],
        "vbal": {
            "files_prefix": "mpas",
            "relations": [
                {
                    "balanced_variable": "chi",
                    "unbalanced_variable": "psi",
                    "diagonal_regression": True,
                },
                {"balanced_variable": "t", "unbalanced_variable": "psi"},
                {"balanced_variable": "ps", "unbalanced_variable": "psi"},
            ],
        },
        "hdiag": {
            "files_prefix": "mpas",
            "drivers": {},
            "sampling": {"distance classes": 10, "distance class width": 1000000.0},
            "variance": {"initial_length_scales": []},
            "fit": {},
            "min_members": 4,
        },
    }


def _vbal_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "vbal" / "case"
    samples = root / "samples"
    run = root / "VBAL"
    samples.mkdir(parents=True)
    run.mkdir()

    for index in range(1, 5):
        (samples / f"PTB_f48mf24_{index:03d}.nc").write_text("sample")

    for name in [
        "bg.nc",
        "namelist.atmosphere_240km",
        "streams.atmosphere_240km",
        "templateFields.240km.nc",
        "mpas_vbal.nc",
        "mpas_sampling.nc",
        "mpas_vbal_local_000004-000001.nc",
        "mpas_sampling_local_000004-000001.nc",
    ]:
        (run / name).write_text(name)

    (run / "run_vbal.yaml").write_text("background:\n  date: '2026-06-22T00:00:00Z'\n")
    write_manifest(
        StageManifest(
            stage="vbal",
            workspace=str(root),
            inputs={"bflow_workspace": str(tmp_path / "bflow")},
            outputs={
                "vbal": str(run / "mpas_vbal.nc"),
                "sampling": str(run / "mpas_sampling.nc"),
            },
            metadata={
                "members": 4,
                "date": "2026-06-22T00:00:00Z",
                "sample_stem": "PTB_f48mf24",
            },
            status="prepared",
        )
    )
    return root


def test_prepare_hdiag_consumes_vbal_workspace_directly(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = importlib.import_module("bmatrix.hdiag_core.prepare")
    vbal = _vbal_workspace(tmp_path)
    output = tmp_path / "hdiag" / "case"

    monkeypatch.setattr(module, "validate_vbal", lambda _: True)
    monkeypatch.setattr(module, "write_hdiag_pbs", lambda config, run_dir: None)

    result = module.prepare(_config(tmp_path), vbal, workspace=output)

    assert result == output
    assert (output / "samples").is_symlink()
    assert (output / "samples").resolve() == (vbal / "samples").resolve()
    assert (output / "vbal").is_symlink()
    assert (output / "vbal").resolve() == (vbal / "VBAL").resolve()
    assert not (output / "samplesUnbalanced").exists()

    rendered = yaml.safe_load((output / "HDIAG" / "run_hdiag.yaml").read_text())
    ensemble = rendered["background error"]["ensemble"]["members from template"]["template"]
    assert ensemble["filename"] == "../samples/PTB_f48mf24_%mem%.nc"
    outer = rendered["background error"]["saber outer blocks"][0]
    assert outer["saber block name"] == "BUMP_VerticalBalance"
    assert outer["read"]["io"]["data directory"] == "../vbal"

    manifest = json.loads((output / "stage-manifest.json").read_text())
    assert manifest["stage"] == "hdiag"
    assert manifest["inputs"] == {"vbal_workspace": str(vbal.resolve())}
    assert manifest["metadata"]["members"] == 4
