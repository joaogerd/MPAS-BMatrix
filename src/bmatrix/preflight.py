"""Side-effect-free preflight checks for the composed MPAS-BMatrix configuration."""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import runtime_contract
from .errors import ConfigurationError


@dataclass(frozen=True)
class ResourceCheck:
    name: str
    path: str
    kind: str
    status: str
    ok: bool
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _path(value: object) -> Path:
    return Path(str(value)).expanduser()


def _missing(name: str, kind: str = "path") -> ResourceCheck:
    return ResourceCheck(name, "<unset>", kind, "NOT_CONFIGURED", False)


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


def _normalized_stack_root(path: Path) -> Path:
    """Accept either the spack-stack checkout or its immediate parent."""
    setup_relative = Path("configs/sites/tier2/jaci/setup.sh")
    if (path / setup_relative).is_file():
        return path
    child = path / "spack-stack"
    if (child / setup_relative).is_file():
        return child
    return path


def check_config_resources(config: Mapping[str, object]) -> list[ResourceCheck]:
    """Validate the filesystem/runtime resources knowable before scientific work."""
    checks: list[ResourceCheck] = []

    project = _mapping(config, "project")
    project_root_value = project.get("project_root")
    work_root_value = project.get("work_root")
    project_root = _path(project_root_value) if project_root_value else None
    if project_root is None:
        checks.append(_missing("project.project_root", "directory"))
    else:
        checks.append(_directory("project.project_root", project_root))
    if not work_root_value:
        checks.append(_missing("project.work_root", "writable directory"))
    else:
        checks.append(_writable_directory("project.work_root", _path(work_root_value)))

    install = _mapping(config, "install")
    install_root_value = install.get("root")
    contract: Mapping[str, object] | None = None
    if not install_root_value:
        checks.append(_missing("install.root", "directory"))
    else:
        install_root = _path(install_root_value)
        checks.append(_directory("install.root", install_root))
        manifest = install_root / "share/monan-jedi/install-manifest.json"
        checks.append(_file("install.runtime_contract", manifest))
        if manifest.is_file():
            try:
                contract = runtime_contract(config)
            except ConfigurationError:
                checks.append(
                    ResourceCheck(
                        "install.runtime_contract_v2",
                        str(manifest),
                        "ecosystem contract v2",
                        "INVALID",
                        False,
                    )
                )
            else:
                checks.append(
                    ResourceCheck(
                        "install.runtime_contract_v2",
                        str(manifest),
                        "ecosystem contract v2",
                        "OK",
                        True,
                    )
                )
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

    environment = _mapping(config, "environment")
    loader = str(environment.get("loader", ""))
    if not loader:
        checks.append(_missing("environment.loader", "file"))
    elif project_root is not None:
        loader_path = _path(loader)
        if not loader_path.is_absolute():
            loader_path = project_root / loader_path
        checks.append(_file("environment.loader", loader_path))

    variables = environment.get("variables", {})
    stack_root_value = variables.get("STACK_ROOT") if isinstance(variables, Mapping) else None
    if not stack_root_value:
        checks.append(_missing("environment.variables.STACK_ROOT", "directory"))
    else:
        stack_root = _normalized_stack_root(_path(stack_root_value))
        checks.append(_directory("environment.variables.STACK_ROOT", stack_root))
        if contract is not None:
            stack_contract = contract.get("stack")
            if isinstance(stack_contract, Mapping):
                site_setup = str(stack_contract["site_setup"])
                env_name = str(stack_contract["env_name"])
                module_template = str(stack_contract["module_root_template"])
                checks.append(
                    _file(
                        "stack.site_setup",
                        stack_root / site_setup,
                    )
                )
                module_root = stack_root / module_template.format(env_name=env_name)
                checks.append(_directory("stack.module_root", module_root))

    mesh = _mapping(config, "mesh")
    grid_value = mesh.get("grid")
    graph_value = mesh.get("graph")
    partitions_value = mesh.get("partitions_dir")
    nproc_value = mesh.get("nproc")

    if not grid_value:
        checks.append(_missing("mesh.grid", "file"))
    else:
        checks.append(_file("mesh.grid", _path(grid_value)))

    if not graph_value:
        checks.append(_missing("mesh.graph", "file"))
    else:
        checks.append(_file("mesh.graph", _path(graph_value)))

    if not partitions_value:
        checks.append(_missing("mesh.partitions_dir", "directory"))
    else:
        partitions_dir = _path(partitions_value)
        checks.append(_directory("mesh.partitions_dir", partitions_dir))
        if nproc_value is None:
            checks.append(_missing("mesh.nproc", "integer"))
        elif graph_value:
            try:
                nproc = int(nproc_value)
            except (TypeError, ValueError):
                checks.append(
                    ResourceCheck(
                        "mesh.nproc",
                        str(nproc_value),
                        "positive integer",
                        "INVALID",
                        False,
                    )
                )
            else:
                if nproc < 1:
                    checks.append(
                        ResourceCheck(
                            "mesh.nproc",
                            str(nproc_value),
                            "positive integer",
                            "INVALID",
                            False,
                        )
                    )
                else:
                    checks.append(
                        ResourceCheck("mesh.nproc", str(nproc), "positive integer", "OK", True)
                    )
                    partition = partitions_dir / (
                        f"{Path(str(graph_value)).name}.part.{nproc}"
                    )
                    checks.append(_file("mesh.partition", partition))

    static = _mapping(config, "static")
    for key in ("invariant", "geovars", "keptvars"):
        value = static.get(key)
        if not value:
            checks.append(_missing(f"static.{key}", "file"))
        else:
            checks.append(_file(f"static.{key}", _path(value)))

    support_key = "support_dir" if static.get("support_dir") else "tutorial_physics_files"
    support_value = static.get(support_key)
    support_dir = _path(support_value) if support_value else None
    if support_dir is not None:
        checks.append(_directory(f"static.{support_key}", support_dir))

    legacy_case = (
        str(mesh.get("name")) == "x1.10242"
        and static.get("tutorial_physics_files")
        and not static.get("namelist")
        and not static.get("streams")
    )
    for key in ("namelist", "streams"):
        explicit = static.get(key)
        if explicit:
            checks.append(_file(f"static.{key}", _path(explicit)))
            continue
        neutral = support_dir / f"{key}.atmosphere" if support_dir else None
        if neutral is not None and neutral.is_file():
            checks.append(_file(f"static.{key}", neutral))
            continue
        if legacy_case and support_dir is not None:
            checks.append(_file(f"static.{key}", support_dir / f"{key}.atmosphere_240km"))
            continue
        checks.append(ResourceCheck(
            f"static.{key}", "<unset>", "file", "NOT_CONFIGURED", False,
            f"Add static.{key}: /absolute/path/to/your/case/{key}.atmosphere "
            "to the case YAML. Use an MPAS file validated for this mesh."
        ))

    selected_lists = static.get("stream_lists", [])
    if selected_lists is None:
        selected_lists = []
    if not isinstance(selected_lists, list) or not all(
        isinstance(name, str) and name and Path(name).name == name
        for name in selected_lists
    ):
        checks.append(ResourceCheck(
            "static.stream_lists", "<invalid>", "list of filenames", "INVALID",
            False, "Set static.stream_lists to a YAML list of valid filenames."
        ))
    elif selected_lists:
        if support_dir is None:
            checks.append(ResourceCheck(
                "static.support_dir", "<unset>", "directory", "NOT_CONFIGURED",
                False, "Set static.support_dir to the directory containing "
                "the files declared in static.stream_lists."
            ))
        else:
            for index, name in enumerate(selected_lists):
                if name == "stream_list.atmosphere.control":
                    continue
                checks.append(_file(f"static.stream_lists[{index}]", support_dir / name))

    return checks


def preflight_payload(config: Mapping[str, object]) -> dict[str, object]:
    checks = check_config_resources(config)
    return {
        "valid": all(item.ok for item in checks),
        "checks": [item.as_dict() for item in checks],
    }

