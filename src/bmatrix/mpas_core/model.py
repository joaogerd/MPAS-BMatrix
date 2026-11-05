from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from ..config import safe_time


DA_STATE_REQUIRED_VARIABLES = [
    "uReconstructZonal",
    "uReconstructMeridional",
    "theta",
    "pressure_p",
    "pressure_base",
    "qv",
    "surface_pressure",
    "qc",
    "qr",
    "qi",
    "qs",
    "qg",
]


def parse_time(t: str) -> datetime:
    return datetime.strptime(t, "%Y-%m-%d_%H:%M:%S")


def fmt_file_time(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d_%H.%M.%S")


def forecast_run_dir(config, init_time: str, lead_hours: int, dt: int) -> Path:
    mesh = config["mesh"]["name"]
    if "nproc" not in config["mesh"]:
        raise ValueError("Declare mesh.nproc in the case YAML (MPI rank count).")
    nproc = int(config["mesh"]["nproc"])
    if nproc < 1:
        raise ValueError("mesh.nproc must be positive.")
    return (
        Path(config["project"]["work_root"])
        / "runs"
        / f"forecast_{mesh}_{safe_time(init_time)}_f{lead_hours:03d}_dt{dt}_np{nproc}"
    )


def restart_file(config, init_time: str, lead_hours: int, dt: int) -> Path:
    valid = parse_time(init_time) + timedelta(hours=lead_hours)
    return forecast_run_dir(config, init_time, lead_hours, dt) / f"restart.{fmt_file_time(valid)}.nc"


def bflow_file(config, init_time: str, lead_hours: int, dt: int) -> Path:
    """Resolve one MPAS input from a user-selected path pattern.

    A producer manifest is preferred. No BMatrix code may guess how MPASWF
    names forecast directories: different sites/campaigns have different
    layouts and science inputs.
    """
    from ..errors import ConfigurationError

    bflow = config.get("bflow", {})
    template = bflow.get("forecast_state_template") if isinstance(bflow, dict) else None
    if not isinstance(template, str) or not template.strip():
        raise ConfigurationError(
            "Os arquivos de previsão não foram informados. Utilize --manifest "
            "com o arquivo produzido pelo MPASWF ou configure "
            "bflow.forecast_state_template para a estrutura de arquivos deste experimento."
        )
    valid = parse_time(init_time) + timedelta(hours=lead_hours)
    mesh = config.get("mesh", {})
    if not isinstance(mesh, dict):
        raise ConfigurationError("O YAML do experimento precisa definir o bloco mesh.")
    context = {
        "mesh_name": str(mesh.get("name", "")),
        "nproc": mesh.get("nproc"),
        "dt": dt,
        "lead_hours": lead_hours,
        "lead_padded": f"{lead_hours:03d}",
        "init_time": init_time,
        "init_compact": safe_time(init_time),
        "init_date_file": fmt_file_time(parse_time(init_time)),
        "valid_time": valid.strftime("%Y-%m-%d_%H:%M:%S"),
        "valid_compact": valid.strftime("%Y%m%d%H"),
        "valid_date_file": fmt_file_time(valid),
    }
    try:
        rendered = template.format(**context)
    except (KeyError, ValueError, IndexError) as exc:
        raise ConfigurationError(
            f"bflow.forecast_state_template possui um marcador inválido: {exc}. "
            "Revise os nomes dos campos documentados para este experimento."
        ) from exc
    path = Path(rendered).expanduser()
    if not path.is_absolute():
        project = config.get("project", {})
        root = project.get("work_root") if isinstance(project, dict) else None
        if not isinstance(root, str) or not root:
            raise ConfigurationError(
                "Configure project.work_root ou use um caminho absoluto "
                "em bflow.forecast_state_template."
            )
        path = Path(root) / path
    return path
