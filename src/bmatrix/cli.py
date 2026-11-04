"""The single public command-line interface for MPAS static B-matrix products."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
from pathlib import Path

from .config import load_config
from .errors import BMatrixError
from .nmc_core.checks import validate_manifest as validate_nmc_manifest
from .pipeline import BuildRequest, STAGES, build, generate_weights, plan, validate
from .preflight import preflight_payload
from .plots_core.runner import generate_plots

def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", required=True, help="Arquivo YAML do experimento ou plataforma.")
    parser.add_argument("--bflow-workspace", type=Path, help="Workspace BFLOW; quando omitido é determinístico.")


def _add_pair_source(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", type=Path, help="TSV de pares NMC já produzidos.")
    parser.add_argument("--start-valid-time", help="Início inclusivo YYYY-MM-DD_HH:MM:SS.")
    parser.add_argument("--end-valid-time", help="Fim inclusivo YYYY-MM-DD_HH:MM:SS.")
    parser.add_argument("--valid-interval-hours", type=int, default=24)
    parser.add_argument("--dt", type=int, help="Passo de tempo MPAS; padrão vem de runtime.config_dt.")


def _add_plot_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--plot-level", type=int, default=None, help="Índice vertical (padrão: nível central da malha).")
    parser.add_argument("--plot-dpi", type=int, default=150, help="Resolução das figuras PNG.")
    parser.add_argument(
        "--plot-variables",
        nargs="+",
        default=None,
        help="Variáveis preferenciais a plotar; por padrão usa controles comuns da B.",
    )
    parser.add_argument("--plots-workspace", type=Path, help="Workspace de saída para figuras e resumos.")


def build_parser() -> argparse.ArgumentParser:
    """Build the one public ``mpas-bmatrix`` CLI parser."""
    parser = argparse.ArgumentParser(
        prog="mpas-bmatrix",
        description="Gera produtos de matriz B MPAS-JEDI/SABER a partir de pares NMC já existentes.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check-config", help="Valida e mostra a configuração resolvida.")
    check.add_argument("--config", required=True)
    check.add_argument("--json", action="store_true", help="Exibe o relatório completo em JSON.")
    check.add_argument("--verbose", action="store_true", help="Inclui verificações bem-sucedidas.")
    check.set_defaults(handler=_check_config)

    check_manifest = sub.add_parser(
        "check-manifest",
        help="Valida o manifest NMC/mpaswf antes de iniciar BFLOW.",
    )
    check_manifest.add_argument("--manifest", type=Path, required=True)
    check_manifest.add_argument("--config", help="Opcional: contrato científico para validar também os da_state.")
    check_manifest.set_defaults(handler=_check_manifest)

    weights = sub.add_parser("weights", help="Gera apenas pesos ESMPy MPAS <-> lat-lon no workspace BFLOW.")
    _add_common(weights)
    _add_pair_source(weights)
    weights.add_argument("--force", action="store_true", help="Regenera ambos os arquivos de peso.")
    weights.set_defaults(handler=_weights)

    build_command = sub.add_parser("build", help="Executa BFLOW, VBAL, HDIAG, NICAS, SO, DIRAC e PLOTS.")
    _add_common(build_command)
    _add_pair_source(build_command)
    build_command.add_argument("--from-stage", choices=STAGES, default="bflow")
    build_command.add_argument("--to-stage", choices=STAGES, default="dirac")
    build_command.add_argument("--clean", action="store_true", help="Remove produtos reproduzíveis antes de cada etapa.")
    build_command.add_argument("--skip-weights", action="store_true", help="Exige pesos ESMF existentes sem regenerá-los.")
    build_command.add_argument("--poll-seconds", type=int, default=30)
    build_command.add_argument("--nicas-parallel", action="store_true", help="Submete controles NICAS em paralelo com merge afterok.")
    build_command.add_argument("--so-variant", default="default", choices=("default", "t-only", "u-only"))
    _add_plot_options(build_command)
    build_command.add_argument("--dry-run", action="store_true", help="Mostra o plano sem criar arquivos ou submeter jobs.")
    build_command.set_defaults(handler=_build)

    validate_command = sub.add_parser("validate", help="Valida uma etapa já concluída.")
    _add_common(validate_command)
    _add_pair_source(validate_command)
    validate_command.add_argument("--stage", required=True, choices=STAGES)
    validate_command.add_argument("--so-variant", default="default", choices=("default", "t-only", "u-only"))
    validate_command.set_defaults(handler=_validate)

    plots = sub.add_parser("plots", help="Gera figuras e resumos dos produtos finais da matriz B.")
    _add_common(plots)
    _add_pair_source(plots)
    _add_plot_options(plots)
    plots.add_argument("--clean", action="store_true", help="Remove figuras/resumos anteriores antes de gerar.")
    plots.set_defaults(handler=_plots)

    products = sub.add_parser("products", help="Mostra os produtos reutilizáveis da matriz B para um workspace BFLOW.")
    _add_common(products)
    _add_pair_source(products)
    products.set_defaults(handler=_products)
    return parser


def _request(args: argparse.Namespace, *, dry_run: bool = False) -> BuildRequest:
    return BuildRequest(
        from_stage=getattr(args, "from_stage", "bflow"),
        to_stage=getattr(args, "to_stage", "so"),
        manifest=getattr(args, "manifest", None),
        start_valid_time=getattr(args, "start_valid_time", None),
        end_valid_time=getattr(args, "end_valid_time", None),
        valid_interval_hours=getattr(args, "valid_interval_hours", 24),
        dt=getattr(args, "dt", None),
        bflow_workspace=getattr(args, "bflow_workspace", None),
        clean=getattr(args, "clean", False),
        skip_weights=getattr(args, "skip_weights", False),
        poll_seconds=getattr(args, "poll_seconds", 30),
        nicas_parallel=getattr(args, "nicas_parallel", False),
        so_variant=getattr(args, "so_variant", "default"),
        plot_level=getattr(args, "plot_level", None),
        plot_dpi=getattr(args, "plot_dpi", 150),
        plot_variables=tuple(getattr(args, "plot_variables", None) or ()),
        plots_workspace=getattr(args, "plots_workspace", None),
        dry_run=dry_run or getattr(args, "dry_run", False),
    )


def _check_config(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    preflight = preflight_payload(config)
    if args.json:
        payload = {**config, "preflight": preflight}
        print(json.dumps(payload, indent=2, default=str, sort_keys=True))
        return 0 if preflight["valid"] else 2

    failures = [item for item in preflight["checks"] if not item["ok"]]
    checks = preflight["checks"]
    if args.verbose:
        for item in checks:
            if item["ok"]:
                print(f"OK: {_human_label(item)} ({item['path']})")

    if not failures:
        print(f"Configuração pronta: {len(checks)} verificações aprovadas.")
        return 0

    print(f"Configuração incompleta: {len(failures)} problema(s) a corrigir:")
    for index, item in enumerate(failures, 1):
        print(f"{index}. {_human_label(item)}")
        if item["path"] not in ("<unset>", "<invalid>"):
            print(f"   Caminho: {item['path']}")
        detail = str(item.get("detail") or "").strip()
        if not detail:
            guidance = {
                "NOT_CONFIGURED": "Declare o campo indicado no YAML do experimento.",
                "MISSING": "Corrija o caminho ou disponibilize o arquivo/diretório.",
                "INVALID": "Revise o valor no YAML; o formato ou conteúdo é inválido.",
                "WRONG_TYPE": "Informe um caminho do tipo esperado.",
                "NOT_READABLE": "Verifique a permissão de leitura.",
                "NOT_ACCESSIBLE": "Verifique a permissão de acesso ao diretório.",
                "NOT_EXECUTABLE": "Verifique a instalação e a permissão de execução.",
                "NOT_WRITABLE": "Selecione um diretório com permissão de escrita.",
                "PARENT_NOT_WRITABLE": "Crie o diretório em um local gravável.",
            }
            detail = guidance.get(str(item["status"]), "Revise este recurso no YAML.")
        print(f"   Correção: {detail}")
    return 2


def _human_label(item: dict[str, object]) -> str:
    """Translate internal resource checks to actual YAML fields and user actions."""
    name = str(item["name"])
    if name == "mesh.partition":
        return "Partição MPI (mesh.graph, mesh.partitions_dir e mesh.nproc)"
    if name == "install.runtime_contract_v2":
        return "Manifesto da instalação MONAN-JEDI (install.root)"
    if name.startswith("install.") and name not in ("install.root", "install.atmosphere_share"):
        return f"Executável/arquivo da instalação MONAN-JEDI: {Path(str(item['path'])).name}"
    if name.startswith("stack."):
        return f"Ambiente de execução: {Path(str(item['path'])).name}"
    return name


def _check_manifest(args: argparse.Namespace) -> int:
    config = load_config(args.config) if args.config else None
    report = validate_nmc_manifest(args.manifest, config=config)
    print(json.dumps(report, indent=2, default=str, sort_keys=True))
    return 0


def _weights(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    request = _request(args)
    resolved = plan(config, request)
    paths = generate_weights(config, resolved.paths.bflow, force=args.force)
    print("\n".join(str(path) for path in paths))
    return 0


def _build(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = build(config, _request(args))
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0


def _validate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    request = _request(args)
    resolved = plan(config, request)
    validate(config, args.stage, resolved.paths, variant=args.so_variant)
    print(f"SUCCESS: {args.stage} validado.")
    return 0


def _plot_level(config: dict[str, object], requested: int | None) -> int:
    """Default to the case's middle vertical level, not the tutorial's level 30."""
    if requested is not None:
        if requested < 0:
            raise ValueError("--plot-level must be zero or greater.")
        return requested
    mesh = config.get("mesh", {})
    if not isinstance(mesh, dict) or not isinstance(mesh.get("nvertlevels"), int):
        raise ValueError("Set mesh.nvertlevels in the case YAML to plot 3D products.")
    nlevels = mesh["nvertlevels"]
    if nlevels < 1:
        raise ValueError("mesh.nvertlevels must be a positive integer.")
    return (nlevels - 1) // 2


def _plots(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    request = _request(args)
    resolved = plan(config, request)
    output = generate_plots(
        resolved.final_products,
        resolved.paths.plots,
        clean=args.clean,
        level=_plot_level(config, args.plot_level),
        dpi=args.plot_dpi,
        variables=args.plot_variables,
    )
    print(json.dumps({key: str(value) for key, value in output.items()}, indent=2, sort_keys=True))
    return 0


def _products(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    resolved = plan(config, _request(args))
    print(json.dumps({key: str(value) for key, value in asdict(resolved.final_products).items()}, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the public command and convert known domain errors into exit code 2."""
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (BMatrixError, FileNotFoundError, ValueError, OSError, RuntimeError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
