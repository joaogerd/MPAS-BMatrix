from __future__ import annotations

from pathlib import Path

import yaml

from bmatrix.config import load_config


def test_inherited_contract_path_is_resolved_from_declaring_yaml(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    overlay_dir = tmp_path / "overlay"
    case_dir.mkdir()
    overlay_dir.mkdir()

    contract = case_dir / "contract.yaml"
    contract.write_text(
        yaml.safe_dump(
            {
                "bflow": {
                    "nmc": {"older_lead_hours": 48, "newer_lead_hours": 24},
                    "products": {},
                    "regridding": {},
                    "wind_transform": {},
                }
            }
        )
    )

    case = case_dir / "case.yaml"
    case.write_text(
        yaml.safe_dump(
            {
                "project": {
                    "project_root": str(tmp_path / "repo"),
                    "work_root": str(tmp_path / "work"),
                },
                "mesh": {"name": "x1.test", "grid": str(tmp_path / "mesh.nc")},
                "runtime": {"config_dt": 60},
                "bmatrix": {"configuration": "contract.yaml"},
            }
        )
    )

    overlay = overlay_dir / "override.yaml"
    overlay.write_text(
        yaml.safe_dump(
            {
                "include": "../case/case.yaml",
                "project": {"work_root": str(tmp_path / "override-work")},
            }
        )
    )

    config = load_config(overlay)

    assert Path(config["bmatrix_contract_path"]) == contract.resolve()
    assert config["project"]["work_root"] == str(tmp_path / "override-work")
