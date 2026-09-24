"""Side-effect-free preflight checks for the composed MPAS-BMatrix configuration."""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class ResourceCheck:
    name: str
    path: str
    kind: str
    status: str
    ok: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _path(value: object) -> Path:
    return Path(str(value)).expanduser()


def _file(name: str, path: Path, *, executable: bool = False) -> ResourceCheck:
    kind = "executable" if executable else "file"
    if not path.exists():
        return ResourceCheck(name, str(path), kind, "MISSING", False)
    if not path.is_file():
        return ResourceCheck(name, str(path), kind, "WRONG_TYPE", False)
    if not os.access(path, os.R_OK):
        return ResourceCheck(name, str(path), kind, "NOT_READABLE", False)
    if executable and not os.access(path, os.X_OK):
        return ResourceCheck(name, str(path), kind, "NOT_EXECUTABLE", False)
    return ResourceCheck(name, str(path), kind, "OK", True)


def _directory(name: str, path: Path) -> ResourceCheck:
    if not path.exists():
        return ResourceCheck(name, str(path), "directory", "MISSING", False)
    if not path.is_dir():
        return ResourceCheck(name, str(path), "directory", "WRONG_TYPE", False)
    if not os.access(path, os.R_OK | os.X_OK):
        return ResourceCheck(name, str(path), "directory", "NOT_ACCESSIBLE", False)
    return ResourceCheck(name, str(path), "directory", "OK", True)


def _writable_directory(name: str, path: Path) -> ResourceCheck:
    if path.exists():
        if not path.is_dir():
            return ResourceCheck(name, str(path), "writable directory", "WRONG_TYPE", False)
        if not os.access(path, os.W_OK | os.X_OK):
            return ResourceCheck(name, str(path), "writable directory", "NOT_WRITABLE", False)
        return ResourceCheck(name, str(path), "writable directory", "OK", True)

    parent = path
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    if not parent.exists():
        return ResourceCheck(name, str(path), "writable directory", "NO_EXISTING_PARENT", False)
    if not parent.is_dir() or not os.access(parent, os.W_OK | os.X_OK):
        return ResourceCheck(name, str(path), "writable directory", "PARENT_NOT_WRITABLE", False)
    return ResourceCheck(name, str(path), "writable directory", "CREATABLE", True)


def _mapping(config: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = config.get(key, {})
    return value if isinstance(value, Mapping) else {}


def check_config_resources(config: Mapping[str, object]) -> list[ResourceCheck]:
    """Validate the filesystem/runtime resources knowable before scientific work."""
    checks: list[ResourceCheck] = []

    project = _mapping(config, "project")
    project_root = _path(project.get("project_root", ""))
    work_root = _path(project.get("work_root", ""))
    checks.append(_directory("project.project_root", project_root))
    checks.append(_writable_directory("project.work_root", work_root))

    environment = _mapping(config, "environment")
    loader = str(environment.get("loader", ""))
    if loader:
        loader_path = _path(loader)
        if not loader_path.is_absolute():
            loader_path = project_root / loader_path
        checks.append(_file("environment.loader", loader_path))

    variables = environment.get("variables", {})
    stack_root_value = variables.get("STACK_ROOT") if isinstance(variables, Mapping) else None
    if stack_root_value:
        stack_root = _path(stack_root_value)
        checks.append(_directory("environment.variables.STACK_ROOT", stack_root))
        checks.append(
            _file(
                "stack.site_setup",
                stack_root / "configs/sites/tier2/jaci/setup.sh",
            )
        )
        env_name = str(
            variables.get("STACK_ENV_NAME", "jaci-mpas-jedi-gcc12-craympich")
            if isinstance(variables, Mapping)
            else "jaci-mpas-jedi-gcc12-craympich"
        )
        module_root_value = (
            variables.get("STACK_MODULE_ROOT") if isinstance(variables, Mapping) else None
        )
        module_root = (
            _path(module_root_value)
            if module_root_value
            else stack_root / "envs" / env_name / "modules"
        )
        checks.append(_directory("stack.module_root", module_root))

    install = _mapping(config, "install")
    install_root = _path(install.get("root", ""))
    checks.append(_directory("install.root", install_root))
    checks.append(
        _file(
            "install.error_covariance_toolbox",
            install_root / "bin" / "mpasjedi_error_covariance_toolbox.x",
            executable=True,
        )
    )
    checks.append(
        _file(
            "install.variational",
            install_root / "bin" / "mpasjedi_variational.x",
            executable=True,
        )
    )
    atmosphere_share = _path(
        install.get("atmosphere_share", install_root / "share/MPAS/core_atmosphere")
    )
    checks.append(_directory("install.atmosphere_share", atmosphere_share))

    mesh = _mapping(config, "mesh")
    if mesh.get("grid"):
        checks.append(_file("mesh.grid", _path(mesh["grid"])))
    if mesh.get("graph"):
        checks.append(_file("mesh.graph", _path(mesh["graph"])))
    if mesh.get("partitions_dir"):
        partitions_dir = _path(mesh["partitions_dir"])
        checks.append(_directory("mesh.partitions_dir", partitions_dir))
        if mesh.get("name") and mesh.get("nproc"):
            partition = partitions_dir / (
                f"{mesh['name']}.graph.info.part.{int(mesh['nproc'])}"
            )
            checks.append(_file("mesh.partition", partition))

    static = _mapping(config, "static")
    for key in ("invariant", "geovars", "keptvars"):
        if static.get(key):
            checks.append(_file(f"static.{key}", _path(static[key])))
    if static.get("tutorial_physics_files"):
        checks.append(
            _directory(
                "static.tutorial_physics_files",
                _path(static["tutorial_physics_files"]),
            )
        )

    return checks


def preflight_payload(config: Mapping[str, object]) -> dict[str, object]:
    checks = check_config_resources(config)
    return {
        "valid": all(item.ok for item in checks),
        "checks": [item.as_dict() for item in checks],
    }
