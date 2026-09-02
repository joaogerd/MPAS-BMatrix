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
from .plots_core.runner import generate_plots

DEFAULT_CONFIG = "configs/jaci-x1.10242.yaml"


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="YAML de plataforma que referencia o contrato científico.")
    parser.add_argument("--bflow-workspace", type=Path, help="Workspace BFLOW; quando omitido é determinístico.")


def _add_pair_source(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", type=Path, help="TSV de pares NMC já produzidos.")
    parser.add_argument("--start-valid-time", help="Início inclusivo YYYY-MM-DD_HH:MM:SS.")
    parser.add_argument("--end-valid-time", help="Fim inclusivo YYYY-MM-DD_HH:MM:SS.")
    parser.add_argument("--valid-interval-hours", type=int, default=24)
    parser.add_argument("--dt", type=int, help="Passo de tempo MPAS; padrão vem de runtime.config_dt.")


def _add_plot_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--plot-level", type=int, default=30, help="Índice vertical usado para variáveis 3D.")
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
    check.add_argument("--config", default=DEFAULT_CONFIG)
    check.set_defaults(handler=_check_config)

    check_manifest = sub.add_parser(
        "check-manifest",
        help="Valida o manifest NMC/mpaswf antes de iniciar BFLOW.",
    )
    check_manifest.add_argument("--manifest", type=Path, required=True)
    check_manifest.set_defaults(handler=_check_manifest)

    weights = sub.add_parser("weights", help="Gera apenas pesos ESMPy MPAS <-> lat-lon no workspace BFLOW.")
    _add_common(weights)
    _add_pair_source(weights)
    weights.add_argument("--force", action="store_true", help="Regenera ambos os arquivos de peso.")
    weights.set_defaults(handler=_weights)

    build_command = sub.add_parser("build", help="Executa BFLOW, VBAL, UNBALANCE, HDIAG, NICAS, SO, DIRAC e PLOTS.")
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
        plot_level=getattr(args, "plot_level", 30),
        plot_dpi=getattr(args, "plot_dpi", 150),
        plot_variables=tuple(getattr(args, "plot_variables", None) or ()),
        plots_workspace=getattr(args, "plots_workspace", None),
        dry_run=dry_run or getattr(args, "dry_run", False),
    )


def _check_config(args: argparse.Namespace) -> int:
    print(json.dumps(load_config(args.config), indent=2, default=str, sort_keys=True))
    return 0


def _check_manifest(args: argparse.Namespace) -> int:
    report = validate_nmc_manifest(args.manifest)
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


def _plots(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    request = _request(args)
    resolved = plan(config, request)
    output = generate_plots(
        resolved.final_products,
        resolved.paths.plots,
        clean=args.clean,
        level=args.plot_level,
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
