"""The single public command-line interface for MPAS static B-matrix products."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
import sys
from pathlib import Path

from .errors import BMatrixError
from .onboarding import (
    SUPPORTED_SITES,
    config_path_rows,
    discover_runtime,
    doctor_checks,
    dump_json,
    load_runtime_config,
    repository_root,
    setup_environment,
)
from .pipeline import BuildRequest, STAGES, build, generate_weights, plan, validate
from .plots_core.runner import generate_plots

DEFAULT_CONFIG = str(repository_root() / "configs" / "jaci-x1.10242.yaml")
_DOMAIN_ERRORS = (BMatrixError, FileNotFoundError, ValueError, OSError, RuntimeError)


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help="YAML de plataforma que referencia o contrato científico.",
    )
    parser.add_argument(
        "--bflow-workspace",
        type=Path,
        help="Workspace BFLOW; quando omitido é determinístico.",
    )


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

    setup = sub.add_parser(
        "setup",
        help="Configura o mínimo necessário para usar MPAS-BMatrix no site selecionado.",
    )
    setup.add_argument("--site", choices=SUPPORTED_SITES, default="jaci")
    setup.add_argument("--workspace", type=Path, help="Raiz de trabalho; no JACI há um default por usuário.")
    setup.set_defaults(handler=_setup)

    doctor = sub.add_parser(
        "doctor",
        help="Verifica ambiente, executáveis, malha e arquivos estáticos antes de rodar.",
    )
    doctor.add_argument("--config", default=DEFAULT_CONFIG)
    doctor.add_argument("--site", choices=SUPPORTED_SITES)
    doctor.add_argument("--json", action="store_true", help="Emite diagnóstico estruturado em JSON.")
    doctor.set_defaults(handler=_doctor)

    paths = sub.add_parser(
        "paths",
        help="Mostra os caminhos resolvidos e explica o papel de cada recurso.",
    )
    paths.add_argument("--config", default=DEFAULT_CONFIG)
    paths.add_argument("--site", choices=SUPPORTED_SITES)
    paths.add_argument("--json", action="store_true", help="Emite os caminhos em JSON.")
    paths.set_defaults(handler=_paths)

    check = sub.add_parser("check-config", help="Valida e resume a configuração resolvida.")
    check.add_argument("--config", default=DEFAULT_CONFIG)
    check.add_argument("--json", action="store_true", help="Mostra a configuração completa em JSON.")
    check.set_defaults(handler=_check_config)

    weights = sub.add_parser(
        "weights",
        help="Gera apenas pesos ESMPy MPAS <-> lat-lon no workspace BFLOW.",
    )
    _add_common(weights)
    _add_pair_source(weights)
    weights.add_argument("--force", action="store_true", help="Regenera ambos os arquivos de peso.")
    weights.set_defaults(handler=_weights)

    build_command = sub.add_parser(
        "build",
        help="Executa BFLOW, VBAL, UNBALANCE, HDIAG, NICAS, SO, DIRAC e PLOTS.",
    )
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


def _config(args: argparse.Namespace):
    config, _ = load_runtime_config(args.config)
    return config


def _setup(args: argparse.Namespace) -> int:
    setup_path, discovery = setup_environment(site=args.site, workspace=args.workspace)
    workspace = discovery.as_environment()["WORK_ROOT"]
    print("MPAS-BMatrix setup")
    print("==================")
    print(f"Site: {discovery.site}")
    print(f"Workspace: {workspace}")
    print(f"User setup: {setup_path}")
    print()
    print("Current pipeline layout:")
    for child in (
        "bmatrix/bflow_preprocessing",
        "bmatrix/covariance",
        "bmatrix/plots",
    ):
        print(f"  {Path(workspace) / child}")
    print()
    unresolved = [item for item in discovery.values if not item.value]
    if unresolved:
        print("Resources not discovered yet (only required if referenced by the selected config):")
        for item in unresolved:
            print(f"  [--] {item.name}: {item.description}")
        print()
    print("Run 'mpas-bmatrix paths' to inspect resolution and 'mpas-bmatrix doctor' to validate the selected config.")
    return 0


def _path_ok(label: str, path: Path) -> bool:
    """Use an executable check for runtime programs and existence for data paths."""
    executable = label.endswith(".x") or "executable" in label.lower()
    if executable:
        return path.is_file() and os.access(path, os.X_OK)
    return path.exists()


def _print_discovery(discovery) -> None:
    for item in discovery.values:
        value = item.value or "<unresolved>"
        print(item.name)
        print(f"  {value}")
        print(f"  source: {item.source}")
        print(f"  role: {item.description}")


def _doctor(args: argparse.Namespace) -> int:
    discovery = discover_runtime(site=args.site)
    try:
        config, discovery = load_runtime_config(args.config, site=discovery.site)
    except _DOMAIN_ERRORS as exc:
        payload = {
            "site": discovery.site,
            "ready": False,
            "configuration_error": str(exc),
            "discovery": discovery.as_dict(),
        }
        if args.json:
            print(dump_json(payload))
        else:
            print("MPAS-BMatrix doctor")
            print("==================")
            print(f"Site: {discovery.site}")
            print()
            print("Path discovery:")
            _print_discovery(discovery)
            print()
            print("[CONFIGURATION ERROR]")
            print(f"  {exc}")
            print()
            print("The selected configuration cannot yet be fully resolved.")
            print("Use 'mpas-bmatrix paths' to inspect the roots and apply an override only when needed.")
        return 1

    checks = doctor_checks(config)
    result = [
        {
            "name": label,
            "path": str(path),
            "role": role,
            "ok": _path_ok(label, path),
        }
        for label, path, role in checks
    ]
    ready = all(item["ok"] for item in result)
    if args.json:
        print(
            dump_json(
                {
                    "site": discovery.site,
                    "ready": ready,
                    "checks": result,
                    "discovery": discovery.as_dict(),
                }
            )
        )
        return 0 if ready else 1

    print("MPAS-BMatrix doctor")
    print("==================")
    print(f"Site: {discovery.site}")
    print(f"Mesh: {config['mesh']['name']}")
    print(f"MPI ranks: {config['mesh'].get('nproc', 'not configured')}")
    print()
    for item in result:
        marker = "OK" if item["ok"] else "MISSING"
        print(f"[{marker}] {item['name']}")
        print(f"       {item['path']}")
        print(f"       {item['role']}")
    print()
    print("READY" if ready else "NOT READY")
    return 0 if ready else 1


def _paths(args: argparse.Namespace) -> int:
    discovery = discover_runtime(site=args.site)
    try:
        config, discovery = load_runtime_config(args.config, site=discovery.site)
    except _DOMAIN_ERRORS as exc:
        if args.json:
            print(
                dump_json(
                    {
                        "site": discovery.site,
                        "complete": False,
                        "configuration_error": str(exc),
                        "discovery": discovery.as_dict(),
                    }
                )
            )
        else:
            print("MPAS-BMatrix path discovery")
            print("==========================")
            print(f"Site: {discovery.site}")
            print()
            _print_discovery(discovery)
            print()
            print("Configuration-specific file paths cannot be fully expanded yet.")
            print(f"  {exc}")
        return 1

    rows = config_path_rows(config)
    if args.json:
        print(
            dump_json(
                {
                    "site": discovery.site,
                    "complete": True,
                    "discovery": discovery.as_dict(),
                    "resolved_paths": [
                        {"name": name, "path": path, "role": role}
                        for name, path, role in rows
                    ],
                }
            )
        )
        return 0

    print("MPAS-BMatrix resolved paths")
    print("===========================")
    print(f"Site: {discovery.site}")
    print()
    for name, path, role in rows:
        print(name)
        print(f"  {path}")
        print(f"  {role}")
    print()
    print("Discovery sources")
    print("-----------------")
    for item in discovery.values:
        print(f"{item.name}: {item.value or '<unresolved>'}")
        print(f"  source: {item.source}")
    return 0


def _check_config(args: argparse.Namespace) -> int:
    config, discovery = load_runtime_config(args.config)
    if args.json:
        print(json.dumps(config, indent=2, default=str, sort_keys=True))
        return 0

    print("MPAS-BMatrix configuration")
    print("==========================")
    print(f"Site: {discovery.site}")
    print(f"Project: {config.get('project', {}).get('name', 'MPAS-BMatrix')}")
    print(f"Mesh: {config['mesh']['name']}")
    print(f"MPI ranks: {config['mesh'].get('nproc', 'not configured')}")
    print(f"Workspace: {config.get('project', {}).get('work_root', '<not configured>')}")
    print()
    print("Configuration sources:")
    for source in config.get("configuration_sources", []):
        print(f"  {source}")
    for source in config.get("bmatrix_contract_sources", []):
        print(f"  {source}")
    print()
    print("Status: VALID")
    print("Use --json to inspect the complete resolved configuration.")
    return 0


def _weights(args: argparse.Namespace) -> int:
    config = _config(args)
    request = _request(args)
    resolved = plan(config, request)
    paths = generate_weights(config, resolved.paths.bflow, force=args.force)
    print("\n".join(str(path) for path in paths))
    return 0


def _build(args: argparse.Namespace) -> int:
    config = _config(args)
    result = build(config, _request(args))
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0


def _validate(args: argparse.Namespace) -> int:
    config = _config(args)
    request = _request(args)
    resolved = plan(config, request)
    validate(config, args.stage, resolved.paths, variant=args.so_variant)
    print(f"SUCCESS: {args.stage} validado.")
    return 0


def _plots(args: argparse.Namespace) -> int:
    config = _config(args)
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
    config = _config(args)
    resolved = plan(config, _request(args))
    print(
        json.dumps(
            {key: str(value) for key, value in asdict(resolved.final_products).items()},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the public command and convert known domain errors into exit code 2."""
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except _DOMAIN_ERRORS as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
