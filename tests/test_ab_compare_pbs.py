from __future__ import annotations

from pathlib import Path

from bmatrix.ab_compare_pbs import _comparison_shell, prepare_compare_job


def _config(tmp_path: Path) -> tuple[dict[str, object], Path, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    loader = project_root / "scripts" / "load_jaci_env.sh"
    loader.parent.mkdir()
    loader.write_text("#!/bin/sh\n")
    config_path = project_root / "configs" / "case.yaml"
    config_path.parent.mkdir()
    config_path.write_text("schema_version: 2\n")
    config: dict[str, object] = {
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
    return config, project_root, config_path


def test_comparison_shell_preserves_spack_pythonpath_and_scans_all_path_pythons() -> None:
    text = _comparison_shell([
        "-m",
        "bmatrix.ab_hdiag",
        "compare-downstream",
        "--config",
        "/project/configs/case.yaml",
    ])

    assert 'export PYTHONPATH="${BMATRIX_PROJECT_SRC}${PYTHONPATH:+:${PYTHONPATH}}"' in text
    assert "IFS=':' read -r -a path_entries <<< \"$PATH\"" in text
    assert "for python_name in python3.11 python3 python" in text
    assert "import numpy, netCDF4" in text
    assert "import bmatrix.ab_hdiag" in text
    assert 'echo "COMPARE_PYTHON=$COMPARE_PYTHON"' in text
    assert '"$COMPARE_PYTHON" -m bmatrix.ab_hdiag compare-downstream' in text
    assert "touch compare.done" in text
    assert "/home2/" not in text


def test_compare_pbs_uses_one_cpu_and_absolute_runtime_contract(
    tmp_path: Path, monkeypatch
) -> None:
    config, project_root, config_path = _config(tmp_path)
    monkeypatch.setenv("MONAN_JEDI_INSTALL_ROOT", str(tmp_path / "install"))
    monkeypatch.delenv("BMATRIX_COMPARE_PYTHON", raising=False)

    workspace = prepare_compare_job(config, config_path, tmp_path / "vbal-case")
    text = (workspace / "qsub_compare_downstream.bash").read_text()

    assert "select=1:ncpus=1:mpiprocs=1:ompthreads=1" in text
    assert "#PBS -q pesqmidi" in text
    assert "#PBS -l walltime=02:00:00" in text
    assert f"BMATRIX_PROJECT_SRC={project_root / 'src'}" in text
    assert f"MONAN_JEDI_INSTALL_ROOT={tmp_path / 'install'}" in text
    assert str(config_path.resolve()) in text
    assert "bmatrix.ab_hdiag" in text
    assert "compare-downstream" in text
    assert "touch compare.done" in text
    assert "/home2/" not in text

    # The rendered PBS must not overwrite the module-provided PYTHONPATH with
    # only the project source directory after sourcing the JACI loader.
    assert f"export PYTHONPATH={project_root / 'src'}" not in text


def test_compare_pbs_accepts_explicit_shared_python_override(tmp_path: Path, monkeypatch) -> None:
    config, _, config_path = _config(tmp_path)
    monkeypatch.setenv("MONAN_JEDI_INSTALL_ROOT", str(tmp_path / "install"))
    shared_python = tmp_path / "shared" / "bin" / "python"
    monkeypatch.setenv("BMATRIX_COMPARE_PYTHON", str(shared_python))

    workspace = prepare_compare_job(config, config_path, tmp_path / "vbal-case")
    text = (workspace / "qsub_compare_downstream.bash").read_text()

    assert f"BMATRIX_COMPARE_PYTHON={shared_python}" in text
    assert "BMATRIX_COMPARE_PYTHON" in text
