from __future__ import annotations

from pathlib import Path

import pytest

from bmatrix.scheduler import bmatrix_job_spec, render_pbs


def _config(tmp_path: Path) -> dict[str, object]:
    return {
        "project": {"project_root": str(tmp_path / "repo")},
        "mesh": {"nproc": 128},
        "pbs": {
            "queues": {"bmatrix": "pesqmidi"},
            "walltime": {"bmatrix": "02:00:00"},
        },
        "environment": {
            "loader": "scripts/load_jaci_env.sh",
            "variables": {
                "STACK_ROOT": "/path/to/spack-stack",
            },
        },
    }


def test_pbs_exports_loader_environment_before_source(tmp_path: Path) -> None:
    spec = bmatrix_job_spec(
        _config(tmp_path),
        name="VBAL",
        run_dir=tmp_path / "run",
        command=("mpiexec", "-n", "128", "/install/bin/toolbox.x", "run_vbal.yaml"),
    )

    rendered = render_pbs(spec)

    export_line = "export STACK_ROOT=/path/to/spack-stack"
    source_line = f"source {tmp_path / 'repo' / 'scripts' / 'load_jaci_env.sh'}"
    assert export_line in rendered
    assert source_line in rendered
    assert rendered.index(export_line) < rendered.index(source_line)


def test_pbs_quotes_loader_environment_values(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config["environment"] = {
        "loader": "scripts/load_jaci_env.sh",
        "variables": {"STACK_ROOT": "/path/with spaces/spack-stack"},
    }

    spec = bmatrix_job_spec(
        config,
        name="VBAL",
        run_dir=tmp_path / "run",
        command=("true",),
    )

    assert "export STACK_ROOT='/path/with spaces/spack-stack'" in render_pbs(spec)


def test_scheduler_rejects_non_mapping_environment_variables(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config["environment"] = {
        "loader": "scripts/load_jaci_env.sh",
        "variables": ["STACK_ROOT"],
    }

    with pytest.raises(ValueError, match="environment.variables"):
        bmatrix_job_spec(
            config,
            name="VBAL",
            run_dir=tmp_path / "run",
            command=("true",),
        )
