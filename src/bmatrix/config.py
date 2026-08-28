"""Configuration loading for the MPAS-JEDI static B-matrix workflow.

The workflow uses composed declarative documents:

* a JACI/site YAML containing paths, scheduler and runtime details;
* a mesh/case YAML containing MPAS mesh and static-file settings;
* a scientific-contract YAML assembled from stage-specific fragments.

Any YAML document may declare an ``include`` key containing one relative path or
a list of relative paths. Included documents are merged in declaration order and
the including document overrides them. Mappings are merged recursively; lists
remain atomic so scientifically ordered sequences are never concatenated by
accident.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any
import os
import re

import yaml

from .errors import ConfigurationError

Config = dict[str, Any]
_ENV_REFERENCE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")


def _load_yaml(path: Path) -> Config:
    """Load one YAML mapping and report configuration errors explicitly."""
    if not path.is_file():
        raise ConfigurationError(f"Configuração não encontrada: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"YAML inválido em {path}: {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ConfigurationError(f"A raiz da configuração deve ser um mapa YAML: {path}")
    return dict(raw)


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> Config:
    """Merge mappings recursively without merging list values implicitly."""
    result: Config = deepcopy(dict(base))
    for key, value in override.items():
        old = result.get(key)
        if isinstance(old, Mapping) and isinstance(value, Mapping):
            result[key] = deep_merge(old, value)
        else:
            result[key] = deepcopy(value)
    return result


def _expand_runtime_alias(value: str) -> str:
    """Expand the legacy MONAN_JEDI_INSTALL name as a compatibility fallback.

    The public variable shared with MONAN-JEDI and mpaswf is now
    ``MONAN_JEDI_INSTALL_ROOT``. Existing user scripts that export only
    ``MONAN_JEDI_INSTALL`` remain valid during the transition.
    """
    if "MONAN_JEDI_INSTALL_ROOT" in os.environ:
        return value
    legacy = os.environ.get("MONAN_JEDI_INSTALL")
    if legacy is None:
        return value
    return value.replace("${MONAN_JEDI_INSTALL_ROOT}", legacy).replace("$MONAN_JEDI_INSTALL_ROOT", legacy)


def expand_env(value: Any) -> Any:
    """Expand environment variables recursively in a decoded YAML value."""
    if isinstance(value, Mapping):
        return {str(key): expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env(item) for item in value]
    if isinstance(value, str):
        return os.path.expandvars(_expand_runtime_alias(value))
    return value


def _unresolved_environment_references(value: Any, path: str = "") -> list[tuple[str, str]]:
    """Return unresolved environment-variable references with YAML key paths."""
    unresolved: list[tuple[str, str]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            unresolved.extend(_unresolved_environment_references(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child = f"{path}[{index}]"
            unresolved.extend(_unresolved_environment_references(item, child))
    elif isinstance(value, str):
        for match in _ENV_REFERENCE.finditer(value):
            unresolved.append((path or "<root>", match.group(1) or match.group(2)))
    return unresolved


def _validate_environment_expansion(config: Mapping[str, Any]) -> None:
    """Fail early when a composed configuration still contains ``${VAR}``."""
    unresolved = _unresolved_environment_references(config)
    if not unresolved:
        return
    details = ", ".join(f"{path} -> {name}" for path, name in unresolved)
    raise ConfigurationError(
        "Variáveis de ambiente não definidas na configuração resolvida: " + details
    )


def _include_paths(path: Path, document: Config) -> tuple[Path, ...]:
    """Remove and resolve the optional ``include`` declaration from a YAML map."""
    raw = document.pop("include", None)
    if raw is None:
        return ()
    if isinstance(raw, str):
        specifications = [raw]
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        specifications = list(raw)
    else:
        raise ConfigurationError(f"include deve ser uma string ou lista de strings: {path}")

    paths: list[Path] = []
    for specification in specifications:
        if not isinstance(specification, str) or not specification.strip():
            raise ConfigurationError(f"Cada item de include deve ser um caminho não vazio: {path}")
        expanded = os.path.expandvars(specification)
        unresolved = _unresolved_environment_references(expanded, "include")
        if unresolved:
            names = ", ".join(name for _, name in unresolved)
            raise ConfigurationError(
                f"Variáveis de ambiente não definidas em include de {path}: {names}"
            )
        candidate = Path(expanded).expanduser()
        if not candidate.is_absolute():
            candidate = path.parent / candidate
        paths.append(candidate.resolve())
    return tuple(paths)


def _load_composed_yaml(path: Path, stack: tuple[Path, ...] = ()) -> tuple[Config, tuple[Path, ...]]:
    """Load one YAML document and recursively merge its declared includes."""
    resolved = path.expanduser().resolve()
    if resolved in stack:
        chain = " -> ".join(str(item) for item in (*stack, resolved))
        raise ConfigurationError(f"Ciclo de include detectado: {chain}")

    document = _load_yaml(resolved)
    includes = _include_paths(resolved, document)
    merged: Config = {}
    sources: list[Path] = []
    for included_path in includes:
        included, included_sources = _load_composed_yaml(included_path, (*stack, resolved))
        merged = deep_merge(merged, included)
        for source in included_sources:
            if source not in sources:
                sources.append(source)

    merged = deep_merge(merged, document)
    if resolved not in sources:
        sources.append(resolved)
    return merged, tuple(sources)


def _contract_declaring_path(platform_path: Path, sources: Sequence[Path]) -> Path:
    """Return the source YAML that declared the effective contract path."""
    for source in reversed(tuple(sources)):
        document = _load_yaml(source)
        bmatrix = document.get("bmatrix")
        if isinstance(bmatrix, Mapping) and "configuration" in bmatrix:
            return source
    return platform_path


def _contract_path(declaring_path: Path, platform: Mapping[str, Any]) -> Path | None:
    """Resolve the effective scientific-contract path against its declaring YAML."""
    bmatrix = platform.get("bmatrix")
    if bmatrix is None:
        return None
    if not isinstance(bmatrix, Mapping):
        raise ConfigurationError("bmatrix deve ser um bloco YAML.")
    specification = bmatrix.get("configuration")
    if specification is None:
        return None
    if not isinstance(specification, str) or not specification.strip():
        raise ConfigurationError("bmatrix.configuration deve ser um caminho YAML não vazio.")
    unresolved = _unresolved_environment_references(specification, "bmatrix.configuration")
    if unresolved:
        names = ", ".join(name for _, name in unresolved)
        raise ConfigurationError(
            "Variáveis de ambiente não definidas em bmatrix.configuration: " + names
        )
    candidate = Path(specification).expanduser()
    return candidate if candidate.is_absolute() else (declaring_path.parent / candidate).resolve()


def load_config(path: str | Path) -> Config:
    """Load the composed platform/case configuration and scientific contract."""
    platform_path = Path(path).expanduser().resolve()
    platform_raw, platform_sources = _load_composed_yaml(platform_path)
    platform = expand_env(platform_raw)
    contract_declaring_path = _contract_declaring_path(platform_path, platform_sources)
    contract_path = _contract_path(contract_declaring_path, platform)

    if contract_path is None:
        merged = dict(platform)
        contract_sources: tuple[Path, ...] = ()
    else:
        contract_raw, contract_sources = _load_composed_yaml(contract_path)
        contract = expand_env(contract_raw)
        merged = deep_merge(contract, platform)
        merged["bmatrix_contract"] = contract
        merged["bmatrix_contract_path"] = str(contract_path)
        merged["bmatrix_contract_sources"] = [str(source) for source in contract_sources]

    merged["configuration_sources"] = [str(source) for source in platform_sources]
    _validate_environment_expansion(merged)
    validate_config_shape(merged)
    return merged


def validate_config_shape(config: Mapping[str, Any]) -> None:
    """Perform lightweight validation shared by all workflow stages."""
    required_maps = ("project", "mesh", "runtime", "bflow")
    missing = [name for name in required_maps if not isinstance(config.get(name), Mapping)]
    if missing:
        raise ConfigurationError("Blocos de configuração obrigatórios ausentes: " + ", ".join(missing))
    mesh = config["mesh"]
    for key in ("name", "grid"):
        if not isinstance(mesh.get(key), str) or not mesh[key]:
            raise ConfigurationError(f"mesh.{key} é obrigatório.")
    bflow = config["bflow"]
    for key in ("nmc", "products", "regridding", "wind_transform"):
        if not isinstance(bflow.get(key), Mapping):
            raise ConfigurationError(f"bflow.{key} deve ser um bloco YAML.")


def safe_time(init_time: str) -> str:
    """Return an MPAS-safe time label with dots instead of colons."""
    return init_time.replace(":", ".")


def ymdh(init_time: str) -> str:
    """Return ``YYYYMMDDHH`` from a standard MPAS timestamp."""
    return init_time[0:4] + init_time[5:7] + init_time[8:10] + init_time[11:13]


def date_part(init_time: str) -> str:
    """Return ``YYYYMMDD`` from a standard MPAS timestamp."""
    return init_time[0:4] + init_time[5:7] + init_time[8:10]


def cycle_part(init_time: str) -> str:
    """Return the UTC cycle hour from a standard MPAS timestamp."""
    return init_time[11:13]
