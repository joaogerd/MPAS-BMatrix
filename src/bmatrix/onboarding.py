"""User-facing environment discovery and diagnostics for MPAS-BMatrix.

The public CLI turns machine conventions into resolved paths without hiding what
was selected. Command arguments and explicit environment variables remain
available as overrides; automatic discovery fills only missing values.
"""
from __future__ import annotations

from dataclasses import dataclass
import getpass
import json
import os
from pathlib import Path
import shutil
from typing import Iterable, Mapping

import yaml

from .config import Config, load_config

USER_CONFIG = Path.home() / ".config" / "mpas-bmatrix" / "setup.yaml"
SUPPORTED_SITES = ("jaci", "generic")


@dataclass(frozen=True, slots=True)
class ResolvedPath:
    name: str
    value: str
    source: str
    description: str

    @property
    def path(self) -> Path:
        return Path(self.value).expanduser()

    @property
    def exists(self) -> bool:
        return bool(self.value) and self.path.exists()


@dataclass(frozen=True, slots=True)
class RuntimeDiscovery:
    site: str
    values: tuple[ResolvedPath, ...]

    def as_environment(self) -> dict[str, str]:
        return {item.name: item.value for item in self.values if item.value}

    def as_dict(self) -> dict[str, object]:
        return {
            "site": self.site,
            "paths": {
                item.name: {
                    "value": item.value,
                    "source": item.source,
                    "description": item.description,
                    "exists": item.exists,
                }
                for item in self.values
            },
        }


def repository_root() -> Path:
    """Return the checkout root for the editable/install layout used by this project."""
    return Path(__file__).resolve().parents[2]


def _read_user_setup(path: Path = USER_CONFIG) -> dict[str, str]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): str(value) for key, value in raw.items() if value is not None}


def detect_site(explicit: str | None = None) -> str:
    if explicit:
        site = explicit.lower()
    elif os.environ.get("MPAS_BMATRIX_SITE"):
        site = os.environ["MPAS_BMATRIX_SITE"].lower()
    else:
        saved = _read_user_setup().get("site", "")
        if saved:
            site = saved.lower()
        elif Path("/p/projetos/monan_das").is_dir():
            site = "jaci"
        else:
            site = "generic"
    if site not in SUPPORTED_SITES:
        raise ValueError(f"Site desconhecido: {site}. Opções: {', '.join(SUPPORTED_SITES)}")
    return site


def default_workspace(site: str) -> Path:
    if site == "jaci":
        return Path("/p/projetos/monan_das") / getpass.getuser() / "work" / "MPAS-BMatrix"
    return Path.home() / "MPAS-BMatrix-work"


def _first_existing(candidates: Iterable[Path]) -> Path | None:
    for candidate in candidates:
        candidate = candidate.expanduser()
        if candidate.exists():
            return candidate.resolve()
    return None


def _latest_glob(pattern: str) -> Path | None:
    candidates = sorted(
        Path("/").glob(pattern.lstrip("/")),
        key=lambda item: item.stat().st_mtime if item.exists() else 0,
    )
    return candidates[-1].resolve() if candidates else None


def _prefix_from_command(command: str) -> Path | None:
    resolved = shutil.which(command)
    if not resolved:
        return None
    path = Path(resolved).resolve()
    return path.parent.parent if path.parent.name == "bin" else path.parent


def _resolved(
    name: str,
    description: str,
    *,
    environment: str | None = None,
    discovered: Path | None = None,
) -> ResolvedPath:
    if environment:
        return ResolvedPath(name, str(Path(environment).expanduser()), "environment", description)
    if discovered is not None:
        return ResolvedPath(name, str(discovered), "discovered", description)
    return ResolvedPath(name, "", "unresolved", description)


def _work_root(site: str, saved: Mapping[str, str], workspace: str | Path | None) -> ResolvedPath:
    description = "Raiz persistente dos workspaces e produtos gerados pelo usuário."
    if workspace is not None:
        return ResolvedPath("WORK_ROOT", str(Path(workspace).expanduser()), "argument", description)
    if os.environ.get("WORK_ROOT"):
        return ResolvedPath("WORK_ROOT", os.environ["WORK_ROOT"], "environment", description)
    if saved.get("workspace"):
        return ResolvedPath("WORK_ROOT", saved["workspace"], "user-config", description)
    return ResolvedPath("WORK_ROOT", str(default_workspace(site)), "site-default", description)


def discover_runtime(
    *,
    site: str | None = None,
    workspace: str | Path | None = None,
) -> RuntimeDiscovery:
    """Resolve current runtime roots with transparent precedence."""
    active_site = detect_site(site)
    saved = _read_user_setup()
    user = getpass.getuser()
    jaci_root = Path("/p/projetos/monan_das") / user

    install = _prefix_from_command("mpasjedi_error_covariance_toolbox.x")
    source = mesh = static = stack = None
    if active_site == "jaci":
        install = install or _first_existing(
            (
                jaci_root / "builds" / "monan-jedi",
                jaci_root / "builds" / "monan-jedi-mpas",
            )
        )
        source = _first_existing((jaci_root / "projects" / "MONAN-JEDI",))
        mesh = _first_existing((jaci_root / "projects" / "mpas_meshes",))
        static = _first_existing(
            (
                jaci_root / "external-inputs" / "MPAS-BMatrix" / "x1.10242" / "static-files",
                jaci_root
                / "external-inputs"
                / "mpasjedi_tutorial202509NCAR"
                / "MPAS_namelist_stream_physics_files",
            )
        )
        stack = _latest_glob(
            f"p/projetos/monan_das/{user}/work/spack-stack-inpe-overlay-*/spack-stack"
        ) or _first_existing((jaci_root / "work" / "spack-stack",))

    if os.environ.get("BMATRIX_ROOT"):
        bmatrix_root = ResolvedPath(
            "BMATRIX_ROOT",
            os.environ["BMATRIX_ROOT"],
            "environment",
            "Checkout do MPAS-BMatrix usado pela CLI e pelos scripts PBS.",
        )
    else:
        bmatrix_root = ResolvedPath(
            "BMATRIX_ROOT",
            str(repository_root()),
            "package",
            "Checkout do MPAS-BMatrix usado pela CLI e pelos scripts PBS.",
        )

    values = (
        bmatrix_root,
        _work_root(active_site, saved, workspace),
        _resolved(
            "MONAN_JEDI_INSTALL",
            "Prefixo da instalação MPAS-JEDI/SABER que contém bin/ e share/.",
            environment=os.environ.get("MONAN_JEDI_INSTALL"),
            discovered=install,
        ),
        _resolved(
            "MPAS_MESH_ROOT",
            "Raiz das malhas MPAS; será substituída pelo catálogo de recursos.",
            environment=os.environ.get("MPAS_MESH_ROOT"),
            discovered=mesh,
        ),
        _resolved(
            "MPAS_JEDI_STATIC_ROOT",
            "Arquivos estáticos validados; futuramente virão de um resource bundle.",
            environment=os.environ.get("MPAS_JEDI_STATIC_ROOT"),
            discovered=static,
        ),
        _resolved(
            "MONAN_JEDI_SOURCE",
            "Checkout usado apenas pelo legado geovars/keptvars; será removido do runtime.",
            environment=os.environ.get("MONAN_JEDI_SOURCE"),
            discovered=source,
        ),
        _resolved(
            "STACK_ROOT",
            "spack-stack usado pelo perfil JACI para carregar o runtime MPAS-JEDI.",
            environment=os.environ.get("STACK_ROOT"),
            discovered=stack,
        ),
    )
    return RuntimeDiscovery(active_site, values)


def apply_runtime(discovery: RuntimeDiscovery) -> None:
    """Fill missing shell variables without replacing explicit non-empty values."""
    for name, value in discovery.as_environment().items():
        if not os.environ.get(name):
            os.environ[name] = value


def load_runtime_config(
    path: str | Path,
    *,
    site: str | None = None,
    workspace: str | Path | None = None,
) -> tuple[Config, RuntimeDiscovery]:
    discovery = discover_runtime(site=site, workspace=workspace)
    apply_runtime(discovery)
    return load_config(path), discovery


def save_setup(*, site: str, workspace: str | Path, path: Path = USER_CONFIG) -> Path:
    """Persist only user choices; machine/resource paths stay discoverable."""
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {"site": detect_site(site), "workspace": str(Path(workspace).expanduser().resolve())}
    target.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return target


def setup_environment(
    *,
    site: str,
    workspace: str | Path | None = None,
) -> tuple[Path, RuntimeDiscovery]:
    """Create only directories that match the current deterministic pipeline layout."""
    active_site = detect_site(site)
    root = Path(workspace).expanduser() if workspace else default_workspace(active_site)
    root.mkdir(parents=True, exist_ok=True)
    for child in (
        "bmatrix/bflow_preprocessing",
        "bmatrix/covariance",
        "bmatrix/plots",
    ):
        (root / child).mkdir(parents=True, exist_ok=True)
    setup_path = save_setup(site=active_site, workspace=root)
    return setup_path, discover_runtime(site=active_site, workspace=root)


def config_path_rows(config: Mapping[str, object]) -> list[tuple[str, str, str]]:
    """Return important resolved paths and their user-facing roles."""
    rows: list[tuple[str, str, str]] = []
    project = config.get("project", {})
    install = config.get("install", {})
    mesh = config.get("mesh", {})
    static = config.get("static", {})
    environment = config.get("environment", {})
    variables = environment.get("variables", {}) if isinstance(environment, Mapping) else {}

    def add(label: str, mapping: object, key: str, role: str) -> None:
        if isinstance(mapping, Mapping) and mapping.get(key):
            rows.append((label, str(mapping[key]), role))

    add("Repository", project, "project_root", "código e templates do MPAS-BMatrix")
    add("Workspace", project, "work_root", "raiz dos workspaces gerados")
    add("MONAN-JEDI install", install, "root", "executáveis e arquivos share/ do runtime")
    add("MPAS atmosphere share", install, "atmosphere_share", "tabelas físicas do MPAS")
    add("UNBALANCE executable", install, "unbalance_executable", "aplicação de K2^-1")
    add("MPAS grid", mesh, "grid", "geometria horizontal da malha")
    add("MPAS graph", mesh, "graph", "grafo usado no particionamento MPI")
    add("Partitions", mesh, "partitions_dir", "partições METIS por número de ranks")
    add("Invariant", static, "invariant", "estado estático/invariante da malha")
    add("Static files", static, "tutorial_physics_files", "namelist, streams e auxiliares")
    add("geovars.yaml", static, "geovars", "definições de GeoVaLs do MPAS-JEDI")
    add("keptvars.yaml", static, "keptvars", "variáveis preservadas pelo MPAS-JEDI")
    add("spack-stack", variables, "STACK_ROOT", "ambiente JACI usado nos jobs PBS")
    return rows


def doctor_checks(config: Mapping[str, object]) -> list[tuple[str, Path, str]]:
    """Build concrete filesystem checks for the resolved x1.10242 configuration."""
    checks = [
        (label, Path(value).expanduser(), role)
        for label, value, role in config_path_rows(config)
    ]

    mesh = config.get("mesh", {})
    if isinstance(mesh, Mapping) and mesh.get("graph") and mesh.get("nproc"):
        graph = Path(str(mesh["graph"])).expanduser()
        partitions = Path(str(mesh.get("partitions_dir", graph.parent))).expanduser()
        nproc = int(mesh["nproc"])
        checks.append(
            (
                f"MPI partition np{nproc}",
                partitions / f"{graph.name}.part.{nproc}",
                "partição da malha compatível com os ranks configurados",
            )
        )

    install = config.get("install", {})
    if isinstance(install, Mapping) and install.get("root"):
        root = Path(str(install["root"])).expanduser()
        for executable, role in (
            ("mpasjedi_error_covariance_toolbox.x", "toolbox SABER/BUMP"),
            ("mpasjedi_variational.x", "validação variacional SO"),
        ):
            checks.append((executable, root / "bin" / executable, role))

    static = config.get("static", {})
    if isinstance(static, Mapping) and static.get("tutorial_physics_files"):
        static_root = Path(str(static["tutorial_physics_files"])).expanduser()
        for filename, role in (
            ("namelist.atmosphere_240km", "configuração MPAS compatível com x1.10242"),
            ("streams.atmosphere_240km", "streams de entrada/saída do MPAS"),
            ("stream_list.atmosphere.analysis", "variáveis do espaço de análise"),
            ("stream_list.atmosphere.background", "variáveis do background"),
            ("stream_list.atmosphere.ensemble", "variáveis das amostras/ensemble"),
        ):
            checks.append((filename, static_root / filename, role))

    if isinstance(install, Mapping) and install.get("atmosphere_share"):
        physics_root = Path(str(install["atmosphere_share"])).expanduser()
        for filename in (
            "CAM_ABS_DATA.DBL",
            "CAM_AEROPT_DATA.DBL",
            "GENPARM.TBL",
            "LANDUSE.TBL",
            "OZONE_DAT.TBL",
            "RRTMG_LW_DATA",
            "RRTMG_LW_DATA.DBL",
            "RRTMG_SW_DATA",
            "RRTMG_SW_DATA.DBL",
            "SOILPARM.TBL",
            "VEGPARM.TBL",
            "VERSION",
        ):
            checks.append((filename, physics_root / filename, "tabela/arquivo físico requerido pelo MPAS"))
    return checks


def dump_json(data: object) -> str:
    return json.dumps(data, indent=2, sort_keys=True, default=str)
