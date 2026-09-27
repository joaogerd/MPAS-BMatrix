from __future__ import annotations

import json
from pathlib import Path

from bmatrix.ab_so_diag_pbs import prepare_so_diag_job


def test_so_diag_pbs_uses_one_cpu_and_isolated_workspace(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    loader = project_root / "scripts" / "load_jaci_env.sh"
    loader.parent.mkdir()
    loader.write_text("#!/bin/sh\n")
    diagnostic = project_root / "scripts" / "compare_so_increments.py"
    diagnostic.write_text("#!/usr/bin/env python3\n")

    install = tmp_path / "install"
    manifest = install / "share" / "monan-jedi" / "install-manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "ecosystem_contract_version": 2,
                "contract": "monan-jedi-runtime-v2",
                "public_anchors": ["MONAN_JEDI_INSTALL_ROOT", "STACK_ROOT"],
                "stack": {
                    "env_name": "jaci-test",
                    "env_module": "test/jedi-mpas-env/2.0.0",
                    "site_setup": "configs/sites/test/setup.sh",
                    "module_root_template": "envs/{env_name}/modules",
                },
            }
        ),
        encoding="utf-8",
    )

    config = {
        "project": {
            "project_root": str(project_root),
            "work_root": str(tmp_path / "work"),
        },
        "environment": {
            "loader": "scripts/load_jaci_env.sh",
            "variables": {"STACK_ROOT": "/runtime/spack-stack"},
        },
        "install": {"root": str(install)},
        "mesh": {"nproc": 128},
        "pbs": {
            "queues": {"bmatrix": "pesqmidi"},
            "walltime": {"bmatrix": "02:00:00"},
        },
    }
    monkeypatch.delenv("BMATRIX_COMPARE_PYTHON", raising=False)

    workspace = prepare_so_diag_job(config, tmp_path / "vbal-case", top=7, log_lines=9)
    text = (workspace / "qsub_so_diagnostic.bash").read_text()

    assert workspace.name == "so-diagnostic-pbs"
    assert "select=1:ncpus=1:mpiprocs=1:ompthreads=1" in text
    assert "#PBS -q pesqmidi" in text
    assert str(diagnostic) in text
    assert f"MONAN_JEDI_INSTALL_ROOT={tmp_path / 'install'}" in text
    assert "materialized/so" in text
    assert "in-memory/so" in text
    assert "--top 7" in text
    assert "--log-lines 9" in text
    assert "/home2/" not in text
