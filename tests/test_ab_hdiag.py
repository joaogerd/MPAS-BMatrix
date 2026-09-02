from __future__ import annotations

from pathlib import Path

import yaml

from bmatrix.ab_hdiag import ab_paths, write_materialized_hdiag_yaml
from bmatrix.hdiag_core.config_files import write_hdiag_yaml


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


def test_ab_paths_are_isolated_from_production_hdiag(tmp_path: Path) -> None:
    config = _config(tmp_path)
    vbal = tmp_path / "work" / "bmatrix" / "covariance" / "vbal" / "case"

    paths = ab_paths(config, vbal)

    assert paths.root == tmp_path / "work" / "bmatrix" / "covariance" / "ab_hdiag" / "case"
    assert paths.materialized_unbalance == paths.root / "materialized" / "unbalance"
    assert paths.materialized_hdiag == paths.root / "materialized" / "hdiag"
    assert paths.in_memory_hdiag == paths.root / "in-memory" / "hdiag"
    assert paths.materialized_hdiag != paths.in_memory_hdiag
    assert not paths.root.exists()


def test_materialized_renderer_differs_only_at_vbal_application_boundary(tmp_path: Path) -> None:
    config = _config(tmp_path)
    candidate_path = tmp_path / "candidate.yaml"
    reference_path = tmp_path / "reference.yaml"

    write_hdiag_yaml(
        config,
        candidate_path,
        nmembers=4,
        date="2026-06-22T00:00:00Z",
        sample_stem="PTB_f48mf24",
    )
    write_materialized_hdiag_yaml(
        config,
        reference_path,
        nmembers=4,
        date="2026-06-22T00:00:00Z",
        sample_stem="PTB_f48mf24",
    )

    candidate = yaml.safe_load(candidate_path.read_text())
    reference = yaml.safe_load(reference_path.read_text())
    cand_be = candidate["background error"]
    ref_be = reference["background error"]

    cand_template = cand_be["ensemble"]["members from template"]["template"]
    ref_template = ref_be["ensemble"]["members from template"]["template"]
    assert cand_template["filename"] == "../samples/PTB_f48mf24_%mem%.nc"
    assert ref_template["filename"] == "../samplesUnbalanced/PTB_f48mf24_%mem%.nc"

    assert cand_be["saber outer blocks"][0]["saber block name"] == "BUMP_VerticalBalance"
    assert "saber outer blocks" not in ref_be

    cand_without_boundary = dict(cand_be)
    ref_without_boundary = dict(ref_be)
    cand_without_boundary.pop("saber outer blocks")
    cand_without_boundary["ensemble"] = yaml.safe_load(yaml.safe_dump(cand_without_boundary["ensemble"]))
    ref_without_boundary["ensemble"] = yaml.safe_load(yaml.safe_dump(ref_without_boundary["ensemble"]))
    cand_without_boundary["ensemble"]["members from template"]["template"]["filename"] = "BOUNDARY"
    ref_without_boundary["ensemble"]["members from template"]["template"]["filename"] = "BOUNDARY"
    assert cand_without_boundary == ref_without_boundary
