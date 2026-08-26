"""User-facing environment resolution and diagnostics for MPAS-BMatrix.

Resolution is deliberately layered:

1. explicit command/user/environment overrides;
2. site profile rules;
3. environment command probes;
4. compatibility fallbacks kept for current deployments.

The doctor validates the fully resolved configuration. It does not search the
filesystem arbitrarily or hide which rule selected a path.
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
DEFAULT_RESOURCE = "x1.10242"
RUNTIME_OVERRIDE_NAMES = (
    "MONAN_JEDI_INSTALL",
    "MPAS_MESH_ROOT",
    "MPAS_JEDI_STATIC_ROOT",
    "MONAN_JEDI_SOURCE",
    "STACK_ROOT",
)


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
    resource: str
    site_profile: str
    resource_catalog: str
    values: tuple[ResolvedPath, ...]

    def as_environment(self) -> dict[str, str]:
        return {item.name: item.value for item in self.values if item.value}

    def as_dict(self) -> dict[str, object]:
        return {
            "site": self.site,
            "resource": self.resource,
            "site_profile": self.site_profile,
            "resource_catalog": self.resource_catalog,
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


def site_profile_path(site: str) -> Path:
    return repository_root() / "configs" / "sites" / f"{site}.yaml"


def resource_catalog_path(resource: str) -> Path:
    return repository_root() / "configs" / "resources" / f"{resource}.yaml"


def _load_yaml_mapping(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label} must contain a YAML mapping: {path}")
    return dict(raw)


def load_site_profile(site: str) -> tuple[dict[str, object], Path]:
    path = site_profile_path(site)
    profile = _load_yaml_mapping(path, "Site profile")
    configured_site = str(profile.get("site", ""))
    if configured_site != site:
        raise ValueError(
            f"Site profile identity mismatch: requested={site} configured={configured_site or '<empty>'}"
        )
    return profile, path


def load_resource_catalog(resource: str) -> tuple[dict[str, object], Path]:
    path = resource_catalog_path(resource)
    catalog = _load_yaml_mapping(path, "Resource catalog")
    metadata = catalog.get("resource", {})
    configured_name = str(metadata.get("name", "")) if isinstance(metadata, Mapping) else ""
    if configured_name != resource:
        raise ValueError(
            "Resource catalog identity mismatch: "
            f"requested={resource} configured={configured_name or '<empty>'}"
        )
    return catalog, path


def _read_user_setup(path: Path | None = None) -> dict[str, object]:
    target = (path or USER_CONFIG).expanduser()
    if not target.is_file():
        return {}
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, Mapping):
        return {}
    return dict(raw)


def _scalar(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    return str(value) if value not in (None, "") else ""


def detect_site(explicit: str | None = None) -> str:
    if explicit:
        site = explicit.lower()
    elif os.environ.get("MPAS_BMATRIX_SITE"):
        site = os.environ["MPAS_BMATRIX_SITE"].lower()
    else:
        saved = _read_user_setup()
        saved_site = _scalar(saved, "site")
        if saved_site:
            site = saved_site.lower()
        elif Path("/p/projetos/monan_das").is_dir():
            site = "jaci"
        else:
            site = "generic"
    if site not in SUPPORTED_SITES:
        raise ValueError(f"Site desconhecido: {site}. Opções: {', '.join(SUPPORTED_SITES)}")
    return site


def _expand_profile_path(value: object) -> Path:
    text = str(value)
    text = text.replace("${USER}", getpass.getuser())
    text = text.replace("${HOME}", str(Path.home()))
    return Path(os.path.expandvars(text)).expanduser()


def default_workspace(site: str) -> Path:
    profile, _ = load_site_profile(site)
    workspace = profile.get("workspace", {})
    if not isinstance(workspace, Mapping) or not workspace.get("default"):
        raise ValueError(f"Site profile does not define workspace.default: {site}")
    return _expand_profile_path(workspace["default"])


def default_resource(site: str) -> str:
    profile, _ = load_site_profile(site)
    resources = profile.get("resources", {})
    if isinstance(resources, Mapping) and resources.get("default"):
        return str(resources["default"])
    return DEFAULT_RESOURCE


def _first_existing(candidates: Iterable[Path]) -> Path | None:
    for candidate in candidates:
        candidate = candidate.expanduser()
        if candidate.exists():
            return candidate.resolve()
    return None


def _latest_glob(pattern: str) -> Path | None:
    expanded = str(_expand_profile_path(pattern))
    candidates = sorted(
        Path("/").glob(expanded.lstrip("/")),
        key=lambda item: item.stat().st_mtime if item.exists() else 0,
    )
    return candidates[-1].resolve() if candidates else None


def _prefix_from_command(command: str) -> Path | None:
    resolved = shutil.which(command)
    if not resolved:
        return None
    path = Path(resolved).resolve()
    return path.parent.parent if path.parent.name == "bin" else path.parent


def _saved_override(saved: Mapping[str, object], name: str) -> str:
    overrides = saved.get("overrides", {})
    if not isinstance(overrides, Mapping):
        return ""
    value = overrides.get(name)
    return str(value) if value not in (None, "") else ""


def _runtime_rule(profile: Mapping[str, object], key: str) -> Mapping[str, object]:
    runtime = profile.get("runtime", {})
    if not isinstance(runtime, Mapping):
        return {}
    rule = runtime.get(key, {})
    return rule if isinstance(rule, Mapping) else {}


def _compatibility_fallback(rule: Mapping[str, object]) -> Path | None:
    globs = rule.get("compatibility_globs", ())
    if isinstance(globs, list):
        for pattern in globs:
            candidate = _latest_glob(str(pattern))
            if candidate is not None:
                return candidate

    candidates = rule.get("compatibility_candidates", ())
    if isinstance(candidates, list):
        return _first_existing(_expand_profile_path(item) for item in candidates)
    return None


def _resolve_runtime_path(
    name: str,
    description: str,
    *,
    profile: Mapping[str, object],
    profile_key: str,
    saved: Mapping[str, object],
) -> ResolvedPath:
    environment = os.environ.get(name)
    if environment:
        return ResolvedPath(name, str(Path(environment).expanduser()), "environment", description)

    configured = _saved_override(saved, name)
    if configured:
        return ResolvedPath(name, str(Path(configured).expanduser()), "user-config", description)

    rule = _runtime_rule(profile, profile_key)
    if rule.get("path"):
        return ResolvedPath(name, str(_expand_profile_path(rule["path"])), "site-profile", description)

    command = str(rule.get("command_probe", ""))
    if command:
        prefix = _prefix_from_command(command)
        if prefix is not None:
            return ResolvedPath(name, str(prefix), "command-probe", description)

    fallback = _compatibility_fallback(rule)
    if fallback is not None:
        return ResolvedPath(name, str(fallback), "compatibility-fallback", description)

    return ResolvedPath(name, "", "unresolved", description)


def _work_root(
    site: str,
    saved: Mapping[str, object],
    workspace: str | Path | None,
) -> ResolvedPath:
    description = "Raiz persistente dos workspaces e produtos gerados pelo usuário."
    if workspace is not None:
        return ResolvedPath("WORK_ROOT", str(Path(workspace).expanduser()), "argument", description)
    if os.environ.get("WORK_ROOT"):
        return ResolvedPath("WORK_ROOT", os.environ["WORK_ROOT"], "environment", description)
    saved_workspace = _scalar(saved, "workspace")
    if saved_workspace:
        return ResolvedPath("WORK_ROOT", saved_workspace, "user-config", description)
    return ResolvedPath("WORK_ROOT", str(default_workspace(site)), "site-profile", description)


def discover_runtime(
    *,
    site: str | None = None,
    workspace: str | Path | None = None,
    resource: str | None = None,
) -> RuntimeDiscovery:
    """Resolve runtime roots using user choices, site rules and visible fallbacks."""
    active_site = detect_site(site)
    saved = _read_user_setup()
    profile, profile_path = load_site_profile(active_site)

    selected_resource = (
        resource
        or _scalar(saved, "resource")
        or str(profile.get("resources", {}).get("default", DEFAULT_RESOURCE))
        if isinstance(profile.get("resources", {}), Mapping)
        else DEFAULT_RESOURCE
    )
    _, catalog_path = load_resource_catalog(selected_resource)

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
        _resolve_runtime_path(
            "MONAN_JEDI_INSTALL",
            "Prefixo da instalação MPAS-JEDI/SABER que contém bin/ e share/.",
            profile=profile,
            profile_key="monan_jedi_install",
            saved=saved,
        ),
        _resolve_runtime_path(
            "MPAS_MESH_ROOT",
            "Raiz física usada para localizar os arquivos de malha do recurso selecionado.",
            profile=profile,
            profile_key="mesh_root",
            saved=saved,
        ),
        _resolve_runtime_path(
            "MPAS_JEDI_STATIC_ROOT",
            "Raiz física dos arquivos estáticos do recurso selecionado.",
            profile=profile,
            profile_key="static_root",
            saved=saved,
        ),
        _resolve_runtime_path(
            "MONAN_JEDI_SOURCE",
            "Checkout transitório usado por geovars/keptvars até o resource bundle incorporá-los.",
            profile=profile,
            profile_key="monan_jedi_source",
            saved=saved,
        ),
        _resolve_runtime_path(
            "STACK_ROOT",
            "spack-stack usado pelo perfil do site para carregar o runtime MPAS-JEDI.",
            profile=profile,
            profile_key="stack_root",
            saved=saved,
        ),
    )
    return RuntimeDiscovery(
        site=active_site,
        resource=selected_resource,
        site_profile=str(profile_path),
        resource_catalog=str(catalog_path),
        values=values,
    )


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
    resource: str | None = None,
) -> tuple[Config, RuntimeDiscovery]:
    discovery = discover_runtime(site=site, workspace=workspace, resource=resource)
    apply_runtime(discovery)
    return load_config(path), discovery


def save_setup(
    *,
    site: str,
    workspace: str | Path,
    resource: str | None = None,
    overrides: Mapping[str, str | Path] | None = None,
    path: Path | None = None,
) -> Path:
    """Persist semantic user choices and only explicitly requested path overrides."""
    target = (path or USER_CONFIG).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    selected_resource = resource or default_resource(site)
    data: dict[str, object] = {
        "site": detect_site(site),
        "workspace": str(Path(workspace).expanduser().resolve()),
        "resource": selected_resource,
    }
    cleaned_overrides = {
        name: str(Path(value).expanduser())
        for name, value in (overrides or {}).items()
        if name in RUNTIME_OVERRIDE_NAMES and str(value)
    }
    if cleaned_overrides:
        data["overrides"] = cleaned_overrides
    target.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return target


def setup_environment(
    *,
    site: str,
    workspace: str | Path | None = None,
    resource: str | None = None,
    overrides: Mapping[str, str | Path] | None = None,
) -> tuple[Path, RuntimeDiscovery]:
    """Create deterministic work directories and persist the selected resolution inputs."""
    active_site = detect_site(site)
    root = Path(workspace).expanduser() if workspace else default_workspace(active_site)
    root.mkdir(parents=True, exist_ok=True)
    for child in (
        "bmatrix/bflow_preprocessing",
        "bmatrix/covariance",
        "bmatrix/plots",
    ):
        (root / child).mkdir(parents=True, exist_ok=True)
    selected_resource = resource or default_resource(active_site)
    setup_path = save_setup(
        site=active_site,
        workspace=root,
        resource=selected_resource,
        overrides=overrides,
    )
    return setup_path, discover_runtime(
        site=active_site,
        workspace=root,
        resource=selected_resource,
    )


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
    add("spack-stack", variables, "STACK_ROOT", "ambiente do site usado nos jobs PBS")
    return rows


def resource_contract_checks(
    config: Mapping[str, object],
    catalog: Mapping[str, object],
) -> list[dict[str, object]]:
    """Check config metadata against the selected logical resource contract."""
    metadata = catalog.get("resource", {})
    mesh = config.get("mesh", {})
    checks: list[dict[str, object]] = []
    if isinstance(metadata, Mapping) and isinstance(mesh, Mapping):
        expected_name = str(metadata.get("name", ""))
        actual_name = str(mesh.get("name", ""))
        if expected_name:
            checks.append(
                {
                    "name": "Resource mesh",
                    "expected": expected_name,
                    "actual": actual_name,
                    "ok": actual_name == expected_name,
                }
            )
        if metadata.get("nVertLevels") is not None and mesh.get("nvertlevels") is not None:
            expected_levels = int(metadata["nVertLevels"])
            actual_levels = int(mesh["nvertlevels"])
            checks.append(
                {
                    "name": "Vertical levels",
                    "expected": expected_levels,
                    "actual": actual_levels,
                    "ok": actual_levels == expected_levels,
                }
            )
    return checks


def doctor_checks(
    config: Mapping[str, object],
    catalog: Mapping[str, object] | None = None,
) -> list[tuple[str, Path, str]]:
    """Build concrete filesystem checks from config plus the logical resource catalog."""
    if catalog is None:
        catalog, _ = load_resource_catalog(DEFAULT_RESOURCE)

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
    runtime = catalog.get("runtime", {})
    if isinstance(install, Mapping) and install.get("root") and isinstance(runtime, Mapping):
        root = Path(str(install["root"])).expanduser()
        executables = runtime.get("required_executables", {})
        if isinstance(executables, Mapping):
            configured_unbalance = str(install.get("unbalance_executable", ""))
            for executable, role in executables.items():
                if str(executable) == "mpasjedi_unbalance_ensemble.x" and configured_unbalance:
                    continue
                checks.append((str(executable), root / "bin" / str(executable), str(role)))

    static = config.get("static", {})
    static_catalog = catalog.get("static", {})
    if (
        isinstance(static, Mapping)
        and static.get("tutorial_physics_files")
        and isinstance(static_catalog, Mapping)
    ):
        static_root = Path(str(static["tutorial_physics_files"])).expanduser()
        required_static = static_catalog.get("required_files", ())
        if isinstance(required_static, list):
            for filename in required_static:
                checks.append(
                    (
                        str(filename),
                        static_root / str(filename),
                        "arquivo estático declarado pelo resource catalog",
                    )
                )

    if (
        isinstance(install, Mapping)
        and install.get("atmosphere_share")
        and isinstance(runtime, Mapping)
    ):
        physics_root = Path(str(install["atmosphere_share"])).expanduser()
        required_physics = runtime.get("required_atmosphere_files", ())
        if isinstance(required_physics, list):
            for filename in required_physics:
                checks.append(
                    (
                        str(filename),
                        physics_root / str(filename),
                        "tabela/arquivo físico declarado pelo resource catalog",
                    )
                )
    return checks


def resolution_warnings(discovery: RuntimeDiscovery) -> list[str]:
    """Explain transitional resolution choices that are valid but not final architecture."""
    fallbacks = [item.name for item in discovery.values if item.source == "compatibility-fallback"]
    if not fallbacks:
        return []
    return [
        "Compatibility fallbacks are in use for: " + ", ".join(fallbacks) + ".",
        "These paths are accepted for the current deployment but are not a canonical shared-site contract.",
    ]


def dump_json(data: object) -> str:
    return json.dumps(data, indent=2, sort_keys=True, default=str)
