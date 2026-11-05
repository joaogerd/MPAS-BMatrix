from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

import yaml

from ..artifacts import MANIFEST_NAME

from .model import so_artifacts
from .static import validate_analysis_output


MPAS_ANALYSIS_VARIABLES = [
    "uReconstructZonal",
    "uReconstructMeridional",
    "theta",
    "qv",
    "surface_pressure",
]

def expected_observation_files(run_dir: Path, variant: str = "default") -> list[str]:
    """Read generated SO observation outputs, not historic T/U file names.

    The fallback is restricted to already-prepared legacy workspaces that
    predate the case-generated SO YAML. A newly prepared case always uses
    its generated observation specification.
    """
    source = run_dir / so_artifacts(variant)["yaml"]
    if not source.is_file():
        legacy = {
            "default": ["obsout_SO_T.h5", "obsout_SO_U.h5"],
            "t-only": ["obsout_SO_T.h5"],
            "u-only": ["obsout_SO_U.h5"],
        }
        if variant not in legacy:
            raise ValueError(
                f"Arquivo de configuração do teste SO não encontrado: {source}. "
                "Prepare esta variante usando o YAML científico antes de validar."
            )
        return list(legacy[variant])
    try:
        document = yaml.safe_load(source.read_text(encoding="utf-8"))
        observers = document["observations"]["observers"]
        if not isinstance(observers, list) or not observers:
            raise ValueError("lista vazia")
        result = []
        for observer in observers:
            raw = observer["obs space"]["obsdataout"]["engine"]["obsfile"]
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError("nome do arquivo observacional vazio")
            filename = Path(raw)
            if filename.is_absolute() or ".." in filename.parts:
                raise ValueError(
                    "nome de saída observacional precisa ficar no diretório de execução"
                )
            result.append(str(filename))
        return list(dict.fromkeys(result))
    except (KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
        raise ValueError(
            f"Não foi possível identificar as saídas observacionais no arquivo "
            f"{source}. Corrija a configuração das observações SO: {exc}"
        ) from exc


def expected_analysis_fields(run_dir: Path) -> list[str]:
    """Resolve fields recorded by the SO preparation; legacy uses MPAS defaults."""
    manifest = run_dir / MANIFEST_NAME
    if not manifest.is_file():
        return list(MPAS_ANALYSIS_VARIABLES)
    import json

    try:
        metadata = json.loads(manifest.read_text(encoding="utf-8")).get("metadata", {})
    except (OSError, ValueError) as exc:
        raise ValueError(f"Manifesto SO inválido em {manifest}: {exc}") from exc
    selected = metadata.get("required_native_analysis_fields")
    if selected is None:
        return list(MPAS_ANALYSIS_VARIABLES)
    if not isinstance(selected, list) or not all(
        isinstance(item, str) and item.strip() for item in selected
    ):
        raise ValueError(
            "Manifesto SO contém uma lista inválida de variáveis de análise. "
            "Revise single_observation.validation_native_analysis_fields."
        )
    return selected


FATAL_LOG_PATTERNS = [
    re.compile(r"ERROR:\s*Requested field\b"),
    re.compile(r"CRITICAL ERROR:\s*xml stream parser failed"),
    re.compile(r"\bABORT\b"),
    re.compile(r"\bFATAL\b"),
    re.compile(r"signal 11"),
    re.compile(r"Jb is NaN"),
]


def so_errors(run_dir: Path, variant: str = "default") -> list[str]:
    artifacts = so_artifacts(variant)
    runlog = run_dir / artifacts["runlog"]
    text = runlog.read_text(errors="replace") if runlog.is_file() else ""
    errors = []
    if "with status = 0" not in text:
        errors.append(f"status final de sucesso ausente no {artifacts['runlog']}")
    if "CostFunction::addIncrement: Analysis" not in text:
        errors.append("CostFunction::addIncrement não chegou em Analysis")
    analysis_files = list(run_dir.glob("an.*.nc"))
    if not analysis_files:
        errors.append("arquivo de análise an.*.nc ausente")
    else:
        try:
            required_fields = expected_analysis_fields(run_dir)
        except ValueError as exc:
            errors.append(str(exc))
        else:
            for path in analysis_files:
                try:
                    validate_analysis_output(path, required_fields)
                except RuntimeError as exc:
                    errors.append(str(exc))
    try:
        expected_files = expected_observation_files(run_dir, variant=variant)
    except ValueError as exc:
        errors.append(str(exc))
    else:
        for name in expected_files:
            if not (run_dir / name).is_file():
                errors.append(f"produto SO ausente: {name}")
    combined = "\n".join(
        path.read_text(errors="replace")
        for path in [runlog, run_dir / artifacts["stdout"], run_dir / artifacts["stderr"]]
        if path.is_file()
    )
    nonzero_statuses = re.findall(r"with status\s*=\s*(-?\d+)", combined)
    if any(status != "0" for status in nonzero_statuses):
        errors.append("status final diferente de zero encontrado nos logs")
    for pattern in FATAL_LOG_PATTERNS:
        match = pattern.search(combined)
        if match:
            errors.append(f"erro fatal encontrado nos logs SO: {match.group(0)}")
            break
    return errors


def check(workspace: str | Path, variant: str = "default") -> bool:
    root = Path(workspace)
    errors = so_errors(root, variant=variant)
    print("=== SO validation ===")
    print(f"WORKSPACE={root}")
    print(f"VARIANT={variant}")
    if errors:
        for error in errors:
            print(f"  - {error}")
        raise SystemExit("ERRO: SO falhou ou ficou incompleto.")
    print("SUCCESS: SO validado.")
    return True
