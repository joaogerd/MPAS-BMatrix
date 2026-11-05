"""Validated accessors for the MPAS-JEDI/SABER scientific contract."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .errors import ConfigurationError


def section(config: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    """Return a required mapping section from a loaded configuration.

    Parameters
    ----------
    config
        Fully merged workflow configuration.
    name
        Required top-level YAML block.

    Returns
    -------
    Mapping[str, Any]
        The validated section.
    """
    value = config.get(name)
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{name} deve ser um bloco YAML.")
    return value


def controls(config: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Return declared B-matrix controls in configured order."""
    raw = config.get("controls")
    if not isinstance(raw, list) or not raw:
        raise ConfigurationError("controls deve ser uma lista não vazia.")
    parsed = tuple(item for item in raw if isinstance(item, Mapping))
    if len(parsed) != len(raw):
        raise ConfigurationError("Cada item de controls deve ser um bloco YAML.")
    for item in parsed:
        if not isinstance(item.get("code"), str) or not isinstance(item.get("file"), str):
            raise ConfigurationError("Cada control requer code e file.")
    return parsed


def control_file_names(config: Mapping[str, Any]) -> tuple[str, ...]:
    """Return physical NetCDF control variable names."""
    return tuple(str(item["file"]) for item in controls(config))


def control_code_names(config: Mapping[str, Any]) -> tuple[str, ...]:
    """Return canonical JEDI control variable names."""
    return tuple(str(item["code"]) for item in controls(config))


def control_aliases(config: Mapping[str, Any]) -> list[dict[str, str]]:
    """Return aliases from canonical JEDI names to B-product file names."""
    return [{"in code": str(item["code"]), "in file": str(item["file"])} for item in controls(config)]


def control_code_to_file(config: Mapping[str, Any]) -> dict[str, str]:
    """Map JEDI control codes to physical NetCDF names."""
    return {str(item["code"]): str(item["file"]) for item in controls(config)}


def control_file_to_code(config: Mapping[str, Any]) -> dict[str, str]:
    """Map physical NetCDF control names to canonical JEDI names."""
    return {str(item["file"]): str(item["code"]) for item in controls(config)}


def normalize_control_code(config: Mapping[str, Any], value: str) -> str:
    """Resolve a control code or physical file name to its canonical JEDI name."""
    code_to_file = control_code_to_file(config)
    if value in code_to_file:
        return value
    file_to_code = control_file_to_code(config)
    if value in file_to_code:
        return file_to_code[value]
    raise ConfigurationError(f"Variável de controle não declarada: {value}")


def normalize_control(config: Mapping[str, Any], value: str) -> str:
    """Resolve a canonical code or physical NetCDF name to its file name."""
    mapping = control_code_to_file(config)
    if value in mapping:
        return mapping[value]
    if value in mapping.values():
        return value
    raise ConfigurationError(f"Variável de controle não declarada: {value}")


def ordered_control_file_names(
    config: Mapping[str, Any], values: object | None = None
) -> tuple[str, ...]:
    """Resolve an optional configured control ordering.

    Parameters
    ----------
    config
        Fully merged workflow configuration.
    values
        ``None`` to keep the global ``controls`` order, or a YAML list containing
        declared control codes and/or physical NetCDF variable names.

    Returns
    -------
    tuple[str, ...]
        Validated physical variable names, without duplicates.
    """
    if values is None:
        return control_file_names(config)
    raw = list_of_strings(values, "ordem de variáveis")
    result = tuple(normalize_control(config, item) for item in raw)
    if len(set(result)) != len(result):
        raise ConfigurationError("A ordem de variáveis contém controles repetidos.")
    return result


def ordered_control_code_names(
    config: Mapping[str, Any], values: object | None = None
) -> tuple[str, ...]:
    """Resolve an optional configured control ordering to canonical JEDI names."""
    if values is None:
        return control_code_names(config)
    raw = list_of_strings(values, "ordem de variáveis")
    result = tuple(normalize_control_code(config, item) for item in raw)
    if len(set(result)) != len(result):
        raise ConfigurationError("A ordem de variáveis contém controles repetidos.")
    return result


def control_read_grids(config: Mapping[str, Any]) -> list[dict[str, dict[str, list[str]]]]:
    """Split canonical control names into 3D and 2D model grids."""
    variables_3d: list[str] = []
    variables_2d: list[str] = []
    for item in controls(config):
        dimensions = str(item.get("dimensions", "3d")).lower()
        variable = str(item["code"])
        if dimensions == "3d":
            variables_3d.append(variable)
        elif dimensions == "2d":
            variables_2d.append(variable)
        else:
            raise ConfigurationError(f"Dimensão de controle inválida para {variable}: {dimensions}")
    grids: list[dict[str, dict[str, list[str]]]] = []
    if variables_3d:
        grids.append({"model": {"variables": variables_3d}})
    if variables_2d:
        grids.append({"model": {"variables": variables_2d}})
    if len(grids) < 2:
        raise ConfigurationError("BUMP_NICAS local requer grids separados para variáveis 3D e 2D.")
    return grids


def require_background_covers_analysis(
    background_variables: object,
    analysis_variables: object,
    context: str,
) -> list[str]:
    """Validate that a State can accept the analysis-space increment."""
    background = list_of_strings(background_variables, f"{context}.background_variables")
    analysis = list_of_strings(analysis_variables, f"{context}.analysis_variables")
    missing = [name for name in analysis if name not in background]
    if missing:
        raise ConfigurationError(
            f"{context}.background_variables deve conter todas as variáveis de saída "
            f"do Control2Analysis; ausentes: {', '.join(missing)}"
        )
    return list(background)


def vbal_composite_aliases(config: Mapping[str, Any], order: object | None = None) -> list[dict[str, str]]:
    """Return aliases for VBAL pair-group names in configured triangular order."""
    codes = ordered_control_code_names(config, order)
    files = ordered_control_file_names(config, order)
    aliases: list[dict[str, str]] = []
    for index, code_2 in enumerate(codes):
        file_2 = files[index]
        for code_1, file_1 in zip(codes[: index + 1], files[: index + 1]):
            aliases.append({"in code": f"{code_1}-{code_2}", "in file": f"{file_1}-{file_2}"})
    return aliases


def vbal_dominant_mode(config: Mapping[str, Any]) -> int:
    """Require an explicit number of VBAL modes consistent with the vertical grid."""
    vbal = section(config, "vbal")
    mesh = section(config, "mesh")
    raw = vbal.get("dominant_mode")
    nlevels = mesh.get("nvertlevels")
    if isinstance(nlevels, bool) or not isinstance(nlevels, int) or nlevels <= 0:
        raise ConfigurationError("Defina mesh.nvertlevels como inteiro positivo.")
    if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= nlevels:
        raise ConfigurationError(
            "Defina vbal.dominant_mode explicitamente como inteiro entre 1 e "
            f"mesh.nvertlevels ({nlevels}); não reutilize automaticamente o valor do tutorial."
        )
    return raw


def bflow_product(config: Mapping[str, Any], name: str) -> str:
    """Return a configured BFLOW product filename.

    Parameters
    ----------
    config
        Fully merged workflow configuration.
    name
        One of ``template``, ``older_full``, ``newer_full`` or ``perturbation``.
    """
    bflow = section(config, "bflow")
    products = bflow.get("products")
    if not isinstance(products, Mapping):
        raise ConfigurationError("bflow.products deve ser um bloco YAML.")
    value = products.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"bflow.products.{name} deve ser um nome de arquivo.")
    filename = Path(value)
    if filename.name != value or filename.suffix != ".nc":
        raise ConfigurationError(
            f"bflow.products.{name} deve ser um nome simples terminado em .nc: {value!r}"
        )
    return value


def bflow_sample_stem(config: Mapping[str, Any]) -> str:
    """Return the canonical staged-sample stem derived from BFLOW perturbations."""
    return Path(bflow_product(config, "perturbation")).stem


def list_of_strings(value: object, name: str) -> tuple[str, ...]:
    """Validate a string list from a YAML contract."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ConfigurationError(f"{name} deve ser uma lista de strings.")
    result = tuple(str(item) for item in value)
    if not all(item for item in result):
        raise ConfigurationError(f"{name} contém item vazio.")
    return result
