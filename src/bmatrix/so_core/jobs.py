from __future__ import annotations

from pathlib import Path

from ..nicas_core.checks import home_failure_files
from ..shell import qsub, wait_for_pbs_job, write_text
from .checks import check, expected_observation_files
from .model import so_artifacts


def clean_outputs(run_dir: Path, variant: str = "default") -> None:
    artifacts = so_artifacts(variant)
    for name in [
        artifacts["runlog"],
        artifacts["stdout"],
        artifacts["stderr"],
        *expected_observation_files(run_dir, variant),
    ]:
        (run_dir / name).unlink(missing_ok=True)
    for path in run_dir.glob("an.*.nc"):
        path.unlink()


def run_job(
    workspace: str | Path,
    wait: bool = False,
    poll_seconds: int = 30,
    retries: int = 2,
    variant: str = "default",
) -> str:
    run_dir = Path(workspace)
    artifacts = so_artifacts(variant)
    retries = max(0, retries)
    for attempt in range(retries + 1):
        clean_outputs(run_dir, variant=variant)
        for path in home_failure_files(run_dir):
            path.unlink()
        jobid = qsub(artifacts["pbs"], run_dir)
        job_id_file = "job_id.txt" if variant == "default" else f"job_id_{variant.replace('-', '_')}.txt"
        write_text(run_dir / job_id_file, jobid + "\n")
        if not wait:
            return jobid
        wait_for_pbs_job(jobid, poll_seconds=poll_seconds)
        if home_failure_files(run_dir):
            if attempt < retries:
                print("Falha PBS/HOME na JACI, ressubmetendo etapa SO.")
                continue
            raise SystemExit(f"ERRO: falha PBS/HOME persistiu no SO após {retries} retries.")
        check(run_dir, variant=variant)
        return jobid
    raise AssertionError("loop de retry SO terminou inesperadamente")
