"""Submit the Single Observation A/B increment diagnostic as a one-CPU PBS job."""
from __future__ import annotations

import argparse
import os
from dataclasses import replace
from pathlib import Path
from typing import Mapping

from .ab_compare_pbs import _comparison_shell
from .ab_hdiag import ab_paths
from .config import load_config
from .scheduler import ResourceRequest, bmatrix_job_spec, render_pbs
from .shell import qsub, wait_for_pbs_job, write_text


def prepare_so_diag_job(
    config: Mapping[str, object],
    vbal_workspace: str | Path,
    *,
    root: str | Path | None = None,
    top: int = 20,
    log_lines: int = 80,
) -> Path:
    vbal = Path(vbal_workspace).resolve()
    paths = ab_paths(config, vbal, root)
    run_dir = paths.root / "so-diagnostic-pbs"
    run_dir.mkdir(parents=True, exist_ok=True)

    project = config.get("project", {})
    if not isinstance(project, Mapping) or not project.get("project_root"):
        raise ValueError("project.project_root é obrigatório para o diagnóstico SO A/B.")
    project_root = Path(str(project["project_root"])).resolve()
    script = project_root / "scripts" / "compare_so_increments.py"
    if not script.is_file():
        raise FileNotFoundError(f"comparador SO não encontrado: {script}")

    install_root = os.environ.get("MONAN_JEDI_INSTALL_ROOT")
    if not install_root:
        raise RuntimeError("MONAN_JEDI_INSTALL_ROOT deve estar definido antes do diagnóstico SO A/B.")

    command_args = [
        str(script),
        str(paths.materialized_so),
        str(paths.in_memory_so),
        "--top",
        str(max(1, top)),
        "--log-lines",
        str(max(1, log_lines)),
    ]
    spec = bmatrix_job_spec(
        config,
        name="bmatrixABSOdiag",
        run_dir=run_dir,
        command=("bash", "-c", _comparison_shell(command_args)),
        stdout="so-diagnostic.stdout.log",
        stderr="so-diagnostic.stderr.log",
    )
    runtime_environment = {
        **spec.environment,
        "BMATRIX_PROJECT_SRC": str(project_root / "src"),
        "MONAN_JEDI_INSTALL_ROOT": install_root,
    }
    compare_python = os.environ.get("BMATRIX_COMPARE_PYTHON")
    if compare_python:
        runtime_environment["BMATRIX_COMPARE_PYTHON"] = compare_python

    spec = replace(
        spec,
        resources=ResourceRequest(
            mpi_ranks=1,
            walltime=spec.resources.walltime,
            queue=spec.resources.queue,
            threads_per_rank=1,
        ),
        environment=runtime_environment,
    )
    pbs = run_dir / "qsub_so_diagnostic.bash"
    write_text(pbs, render_pbs(spec))
    print("=== SO A/B diagnostic PBS ===")
    print(f"WORKSPACE={run_dir}")
    print("NCPUS=1")
    print(f"PBS={pbs}")
    return run_dir


def submit_so_diag_job(workspace: str | Path, *, poll_seconds: int = 30) -> str:
    root = Path(workspace)
    for name in ("compare.done", "so-diagnostic.stdout.log", "so-diagnostic.stderr.log", "job_id.txt"):
        (root / name).unlink(missing_ok=True)

    jobid = qsub("qsub_so_diagnostic.bash", root)
    write_text(root / "job_id.txt", jobid + "\n")
    wait_for_pbs_job(jobid, poll_seconds=poll_seconds)

    stdout = root / "so-diagnostic.stdout.log"
    stderr = root / "so-diagnostic.stderr.log"
    if stdout.is_file():
        text = stdout.read_text(errors="replace").strip()
        if text:
            print(text)
    if not (root / "compare.done").is_file():
        if stderr.is_file():
            text = stderr.read_text(errors="replace").strip()
            if text:
                print("=== SO diagnostic stderr ===")
                print(text)
        raise SystemExit("ERRO: diagnóstico SO A/B falhou.")
    print("SUCCESS: diagnóstico SO A/B concluído.")
    return jobid


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run SO A/B increment and convergence diagnostics on one PBS CPU.")
    parser.add_argument("--config", default="configs/jaci-x1.10242.yaml")
    parser.add_argument("--vbal-workspace", type=Path, required=True)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--log-lines", type=int, default=80)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    workspace = prepare_so_diag_job(
        config,
        args.vbal_workspace,
        root=args.root,
        top=args.top,
        log_lines=args.log_lines,
    )
    submit_so_diag_job(workspace, poll_seconds=args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
