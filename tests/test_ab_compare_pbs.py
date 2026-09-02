from __future__ import annotations

from pathlib import Path

from bmatrix.ab_compare_pbs import prepare_compare_job


def test_compare_pbs_uses_one_cpu_and_absolute_runtime_paths(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    loader = project_root / "scripts" / "load_jaci_env.sh"
    loader.parent.mkdir()
    loader.write_text("#!/bin/sh\n")
    config_path = project_root / "configs" / "case.yaml"
    config_path.parent.mkdir()
    config_path.write_text("schema_version: 2\n")

    config = {
        "project": {
            "project_root": str(project_root),
            "work_root": str(tmp_path / "work"),
        },
        "environment": {"loader": "scripts/load_jaci_env.sh", "variables": {}},
        "mesh": {"nproc": 128},
        "pbs": {
            "queues": {"bmatrix": "pesqmidi"},
            "walltime": {"bmatrix": "02:00:00"},
        },
    }
    monkeypatch.setenv("MONAN_JEDI_INSTALL_ROOT", str(tmp_path / "install"))

    workspace = prepare_compare_job(
        config,
        config_path,
        tmp_path / "vbal-case",
    )
    text = (workspace / "qsub_compare_downstream.bash").read_text()

    assert "select=1:ncpus=1:mpiprocs=1:ompthreads=1" in text
    assert "#PBS -q pesqmidi" in text
    assert "#PBS -l walltime=02:00:00" in text
    assert f"PYTHONPATH={project_root / 'src'}" in text
    assert f"MONAN_JEDI_INSTALL_ROOT={tmp_path / 'install'}" in text
    assert str(config_path.resolve()) in text
    assert "bmatrix.ab_hdiag compare-downstream" in text
    assert "touch compare.done" in text
