"""Submit the downstream A/B NetCDF comparison as a one-CPU PBS job."""
from __future__ import annotations

import argparse
import os
import shlex
from dataclasses import replace
from pathlib import Path
from typing import Mapping

from .ab_hdiag import ab_paths
from .config import load_config
from .scheduler import ResourceRequest, bmatrix_job_spec, render_pbs
from .shell import qsub, wait_for_pbs_job, write_text


def _comparison_shell(command_args: list[str]) -> str:
    """Resolve a Python with required modules on the compute node and run comparison."""
    quoted_args = " ".join(shlex.quote(part) for part in command_args)
    return f'''\
python_candidates=()
if [[ -n "${{BMATRIX_COMPARE_PYTHON:-}}" ]]; then
  python_candidates+=("${{BMATRIX_COMPARE_PYTHON}}")
fi
python_candidates+=(python3 python)

COMPARE_PYTHON=""
for raw_candidate in "${{python_candidates[@]}}"; do
  candidate=""
  if [[ "$raw_candidate" == */* ]]; then
    if [[ -x "$raw_candidate" ]]; then
      candidate="$raw_candidate"
    fi
  else
    candidate="$(command -v "$raw_candidate" 2>/dev/null || true)"
  fi
  [[ -n "$candidate" ]] || continue
  if "$candidate" -c 'import numpy, netCDF4' >/dev/null 2>&1; then
    COMPARE_PYTHON="$candidate"
    break
  fi
done

if [[ -z "$COMPARE_PYTHON" ]]; then
  echo "ERRO: nenhum Python acessível no compute node fornece numpy e netCDF4." >&2
  echo "PATH=$PATH" >&2
  echo "BMATRIX_COMPARE_PYTHON=${{BMATRIX_COMPARE_PYTHON:-}}" >&2
  for raw_candidate in "${{python_candidates[@]}}"; do
    if [[ "$raw_candidate" == */* ]]; then
      resolved="$raw_candidate"
    else
      resolved="$(command -v "$raw_candidate" 2>/dev/null || true)"
    fi
    echo "candidate=$raw_candidate resolved=${{resolved:-<not-found>}}" >&2
  done
  exit 2
fi

echo "COMPARE_PYTHON=$COMPARE_PYTHON"
"$COMPARE_PYTHON" {quoted_args}
touch compare.done
'''


def prepare_compare_job(
    config: Mapping[str, object],
    config_path: str | Path,
    vbal_workspace: str | Path,
    *,
    root: str | Path | None = None,
    rtol: float = 1.0e-6,
    atol: float = 1.0e-8,
) -> Path:
    """Render an isolated one-CPU PBS job for the complete downstream comparison."""
    vbal = Path(vbal_workspace).resolve()
    paths = ab_paths(config, vbal, root)
    run_dir = paths.root / "compare-pbs"
    run_dir.mkdir(parents=True, exist_ok=True)

    project = config.get("project", {})
    if not isinstance(project, Mapping) or not project.get("project_root"):
        raise ValueError("project.project_root é obrigatório para o job de comparação A/B.")
    project_root = Path(str(project["project_root"])).resolve()

    install_root = os.environ.get("MONAN_JEDI_INSTALL_ROOT")
    if not install_root:
        raise RuntimeError("MONAN_JEDI_INSTALL_ROOT deve estar definido antes de preparar a comparação A/B.")

    resolved_config = Path(config_path).resolve()
    command_args = [
        "-m",
        "bmatrix.ab_hdiag",
        "compare-downstream",
        "--config",
        str(resolved_config),
        "--vbal-workspace",
        str(vbal),
        "--rtol",
        str(rtol),
        "--atol",
        str(atol),
    ]
    if root is not None:
        command_args.extend(["--root", str(Path(root).resolve())])

    spec = bmatrix_job_spec(
        config,
        name="bmatrixABCompare",
        run_dir=run_dir,
        command=("bash", "-c", _comparison_shell(command_args)),
        stdout="compare.stdout.log",
        stderr="compare.stderr.log",
    )
    runtime_environment = {
        **spec.environment,
        "PYTHONPATH": str(project_root / "src"),
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
    pbs = run_dir / "qsub_compare_downstream.bash"
    write_text(pbs, render_pbs(spec))
    print("=== A/B downstream comparison PBS ===")
    print(f"WORKSPACE={run_dir}")
    print("NCPUS=1")
    print("PYTHON=resolved-on-compute-node")
    print(f"PBS={pbs}")
    return run_dir


def submit_compare_job(workspace: str | Path, *, poll_seconds: int = 30) -> str:
    """Submit, wait for and validate the comparison marker; print concise summaries."""
    root = Path(workspace)
    for name in ("compare.done", "compare.stdout.log", "compare.stderr.log", "job_id.txt"):
        (root / name).unlink(missing_ok=True)

    jobid = qsub("qsub_compare_downstream.bash", root)
    write_text(root / "job_id.txt", jobid + "\n")
    wait_for_pbs_job(jobid, poll_seconds=poll_seconds)

    stdout = root / "compare.stdout.log"
    stderr = root / "compare.stderr.log"
    if stdout.is_file():
        text = stdout.read_text(errors="replace").strip()
        if text:
            print(text)
    if not (root / "compare.done").is_file():
        if stderr.is_file():
            text = stderr.read_text(errors="replace").strip()
            if text:
                print("=== comparison stderr ===")
                print(text)
        raise SystemExit("ERRO: comparação A/B downstream falhou; compare.done não foi produzido.")
    print("SUCCESS: comparação A/B downstream validada em PBS.")
    return jobid


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run complete downstream A/B comparison as a one-CPU PBS job.")
    parser.add_argument("--config", default="configs/jaci-x1.10242.yaml")
    parser.add_argument("--vbal-workspace", type=Path, required=True)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--rtol", type=float, default=1.0e-6)
    parser.add_argument("--atol", type=float, default=1.0e-8)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    workspace = prepare_compare_job(
        config,
        args.config,
        args.vbal_workspace,
        root=args.root,
        rtol=args.rtol,
        atol=args.atol,
    )
    submit_compare_job(workspace, poll_seconds=args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
