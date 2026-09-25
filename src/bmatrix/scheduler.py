"""Scheduler-independent job model and PBS Pro rendering."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shlex
from typing import Mapping, Sequence

from .config import runtime_contract


@dataclass(frozen=True, slots=True)
class ResourceRequest:
    """Resources requested by one HPC job."""

    mpi_ranks: int
    walltime: str
    queue: str | None = None
    threads_per_rank: int = 1

    def __post_init__(self) -> None:
        if self.mpi_ranks < 1:
            raise ValueError("mpi_ranks deve ser positivo.")
        if self.threads_per_rank < 1:
            raise ValueError("threads_per_rank deve ser positivo.")


@dataclass(frozen=True, slots=True)
class JobSpec:
    """Application-neutral executable job rendered by a scheduler adapter."""

    name: str
    working_directory: Path
    command: Sequence[str]
    resources: ResourceRequest
    environment: Mapping[str, str] = field(default_factory=dict)
    bootstrap: Sequence[str] = field(default_factory=tuple)
    stdout: str = "stdout.log"
    stderr: str = "stderr.log"
    preamble: Sequence[str] = field(default_factory=tuple)


def _configured_runtime_environment(environment: Mapping[str, object]) -> dict[str, str]:
    """Return environment variables that must exist before the loader is sourced.

    Parameters
    ----------
    environment
        The composed ``environment`` YAML section. Optional ``variables`` must be
        a mapping of shell-variable names to scalar values.

    Returns
    -------
    dict[str, str]
        Variables rendered explicitly into every PBS script before the
        repository-local environment loader is sourced.
    """
    raw = environment.get("variables", {})
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError("environment.variables deve ser um bloco YAML.")
    result: dict[str, str] = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not name:
            raise ValueError("Cada nome em environment.variables deve ser uma string não vazia.")
        if isinstance(value, (Mapping, list, tuple, set)):
            raise ValueError(f"environment.variables.{name} deve ser um valor escalar.")
        result[name] = str(value)
    return result


def mpi_command(
    config: Mapping[str, object],
    mpi_ranks: int,
    *arguments: object,
) -> tuple[str, ...]:
    """Build one MPI argv from the site scheduler configuration.

    pbs.launcher is an optional list of argv tokens and may use the
    {mpi_ranks} placeholder. The portable default is mpiexec -n {mpi_ranks}.
    Scientific stages provide only their executable and arguments, so launcher
    policy has one owner.
    """
    pbs = config.get("pbs", {})
    if not isinstance(pbs, Mapping):
        raise ValueError("pbs deve ser um bloco YAML.")
    raw = pbs.get("launcher", ["mpiexec", "-n", "{mpi_ranks}"])
    if not isinstance(raw, list) or not raw or not all(
        isinstance(item, str) and item for item in raw
    ):
        raise ValueError("pbs.launcher deve ser uma lista não vazia de strings.")
    launcher = tuple(
        item.replace("{mpi_ranks}", str(mpi_ranks))
        for item in raw
    )
    return (*launcher, *(str(item) for item in arguments))

def bmatrix_job_spec(
    config: Mapping[str, object],
    *,
    name: str,
    run_dir: Path,
    command: Sequence[str],
    stdout: str = "stdout.log",
    stderr: str = "stderr.log",
) -> JobSpec:
    """Create the standard B-matrix job specification from platform settings."""
    mesh = config["mesh"]  # type: ignore[index]
    pbs = config.get("pbs", {})  # type: ignore[union-attr]
    project = config["project"]  # type: ignore[index]
    environment = config["environment"]  # type: ignore[index]
    if not isinstance(mesh, Mapping) or not isinstance(pbs, Mapping):
        raise ValueError("Configuração de mesh/pbs inválida.")
    if not isinstance(project, Mapping) or not isinstance(environment, Mapping):
        raise ValueError("Configuração de project/environment inválida.")
    ranks = int(mesh.get("nproc", pbs.get("nproc", 1)))
    queue = str(pbs.get("queues", {}).get("bmatrix", pbs.get("queue", ""))) or None
    walltime = str(pbs.get("walltime", {}).get("bmatrix", pbs.get("walltime_short", "00:10:00")))
    loader = str(environment["loader"])
    project_root = str(project["project_root"])

    runtime_environment = _configured_runtime_environment(environment)

    # Stack identity is owned by the installed MONAN-JEDI runtime contract.
    # Generated PBS jobs export it explicitly before sourcing the repository
    # loader, so compute nodes cannot drift to the loader's legacy defaults.
    contract = runtime_contract(config)
    stack_contract = contract["stack"]
    stack_root = runtime_environment.get("STACK_ROOT")
    if not stack_root:
        raise ValueError("environment.variables.STACK_ROOT é obrigatório.")
    install = config.get("install", {})
    if not isinstance(install, Mapping) or not install.get("root"):
        raise ValueError("install.root é obrigatório.")
    env_name = str(stack_contract["env_name"])
    module_root = str(Path(stack_root) / str(stack_contract["module_root_template"]).format(env_name=env_name))
    runtime_environment.update(
        {
            "MONAN_JEDI_INSTALL_ROOT": str(install["root"]),
            "STACK_ENV_NAME": env_name,
            "STACK_SITE_SETUP": str(stack_contract["site_setup"]),
            "STACK_ENV_MODULE": str(stack_contract["env_module"]),
            "STACK_MODULE_ROOT": module_root,
            "OMP_NUM_THREADS": "1",
            "GFORTRAN_CONVERT_UNIT": "big_endian:101-200",
            "FI_CXI_RX_MATCH_MODE": "hybrid",
        }
    )

    bootstrap = tuple(
        [
            *(
                f"export {name}={shlex.quote(value)}"
                for name, value in runtime_environment.items()
                if name.startswith("STACK_") or name == "MONAN_JEDI_INSTALL_ROOT"
            ),
            f"source {shlex.quote(str(Path(project_root) / loader))}",
        ]
    )

    return JobSpec(
        name=name,
        working_directory=run_dir,
        command=tuple(command),
        resources=ResourceRequest(mpi_ranks=ranks, walltime=walltime, queue=queue),
        bootstrap=bootstrap,
        environment={
            "OMP_NUM_THREADS": runtime_environment["OMP_NUM_THREADS"],
            "GFORTRAN_CONVERT_UNIT": runtime_environment["GFORTRAN_CONVERT_UNIT"],
            "FI_CXI_RX_MATCH_MODE": runtime_environment["FI_CXI_RX_MATCH_MODE"],
        },
        stdout=stdout,
        stderr=stderr,
        preamble=("ulimit -s unlimited || true",),
    )


def render_pbs(spec: JobSpec) -> str:
    """Render a readable PBS Pro script from a generic job specification."""
    resources = spec.resources
    ncpus = resources.mpi_ranks * resources.threads_per_rank
    lines = [
        "#!/usr/bin/env bash",
        f"#PBS -N {spec.name}",
        "#PBS -j oe",
        f"#PBS -l select=1:ncpus={ncpus}:mpiprocs={resources.mpi_ranks}:ompthreads={resources.threads_per_rank}",
        f"#PBS -l walltime={resources.walltime}",
    ]
    if resources.queue:
        lines.append(f"#PBS -q {resources.queue}")
    lines.extend(["", "set -euo pipefail", ""])
    lines.extend(spec.bootstrap)
    lines.append(f"cd {shlex.quote(str(spec.working_directory))}")
    for name, value in spec.environment.items():
        lines.append(f"export {name}={shlex.quote(value)}")
    lines.extend(spec.preamble)
    lines.append(f"rm -f {shlex.quote(spec.stdout)} {shlex.quote(spec.stderr)}")
    command = shlex.join([str(part) for part in spec.command])
    lines.append(f"{command} > {shlex.quote(spec.stdout)} 2> {shlex.quote(spec.stderr)}")
    return "\n".join(lines) + "\n"
