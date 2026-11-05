from __future__ import annotations

import yaml

from bmatrix.vbal_core.config_files import write_vbal_yaml


# The scientific configuration uses snake_case; SABER reads literal labels with spaces.
def test_vbal_yaml_uses_saber_driver_labels(tmp_path):
    config = {
        "mesh": {"name": "x1.test", "nvertlevels": 55},
        "controls": [
            {"code": "psi", "file": "stream_function"},
            {"code": "chi", "file": "velocity_potential"},
        ],
        "bflow": {"products": {"perturbation": "PTB_f48mf24.nc"}},
        "vbal": {
            "dominant_mode": 20,
            "drivers": {
                "write_local_sampling": True,
                "write_global_sampling": True,
                "compute_vertical_covariance": True,
                "compute_vertical_balance": True,
                "write_vertical_balance": True,
            },
            "relations": [
                {"balanced_variable": "chi", "unbalanced_variable": "psi"},
            ],
        },
    }
    output = tmp_path / "run_vbal.yaml"

    write_vbal_yaml(config, output, nmembers=4, date="2026-06-22T00:00:00Z")

    rendered = yaml.safe_load(output.read_text())
    drivers = rendered["background error"]["saber outer blocks"][0]["calibration"]["drivers"]
    assert drivers == {
        "write local sampling": True,
        "write global sampling": True,
        "compute vertical covariance": True,
        "compute vertical balance": True,
        "write vertical balance": True,
    }
    assert all("_" not in key for key in drivers)
