"""Single-entry orchestration for static MPAS-JEDI/SABER B-matrix products."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Mapping

from .bflow_core.manifest import read_manifest
from .bflow_core.model import BflowPair, build_pairs_from_range, default_workspace
from .bflow_core.runner import run_bflow_pipeline
from .bflow_core.weights import generate_esmf_weights
from .bflow_core.workspace import prepare_workspace as prepare_bflow
from .errors import ConfigurationError, WorkflowError
from .dirac_core.prepare import prepare as prepare_dirac
from .dirac_core.runner import submit as submit_dirac, validate as validate_dirac
from .dirac_core.model import dirac_workspace
from .hdiag_core.prepare import prepare as prepare_hdiag
from .hdiag_core.runner import submit as submit_hdiag, validate as validate_hdiag
from .hdiag_core.model import hdiag_workspace
from .nicas_core.prepare import prepare as prepare_nicas
from .nicas_core.runner import submit as submit_nicas, validate as validate_nicas
from .nicas_core.model import nicas_workspace
from .plots_core.runner import (
    generate_plots,
    plots_workspace_from_bflow,
    validate_plots,
)
from .products import BMatrixProducts
from .so_core.prepare import prepare as prepare_so
from .so_core.runner import submit as submit_so, validate as validate_so
from .so_core.model import so_workspace
from .vbal_core.model import vbal_workspace
from .vbal_core.runner import prepare as prepare_vbal, submit as submit_vbal, validate as validate_vbal

StageName = Literal["bflow", "vbal", "hdiag", "nicas", "so", "dirac", "plots"]
STAGES: tuple[StageName, ...] = ("bflow", "vbal", "hdiag", "nicas", "so", "dirac", "plots")


@dataclass(frozen=True, slots=True)
class PipelinePaths:
    """Deterministic workspaces for one B-matrix calibration run."""

    bflow: Path
    vbal: Path
    hdiag: Path
    nicas: Path
    so: Path
    dirac: Path
    plots: Path

    @classmethod
    def from_bflow(
        cls,
        config: Mapping[str, object],
        bflow: str | Path,
        plots: str | Path | None = None,
    ) -> "PipelinePaths":
        """Resolve all downstream workspaces from the BFLOW workspace name."""
        bflow_path = Path(bflow).resolve()
        vbal = vbal_workspace(config, bflow_path)
        hdiag = hdiag_workspace(config, vbal)
        nicas = nicas_workspace(config, hdiag)
        return cls(
            bflow=bflow_path,
            vbal=vbal,
            hdiag=hdiag,
            nicas=nicas,
            so=so_workspace(config, nicas),
            dirac=dirac_workspace(config, nicas),
            plots=Path(plots).resolve() if plots else plots_workspace_from_bflow(config, bflow_path),
        )

    def as_strings(self) -> dict[str, str]:
        """Return JSON-ready workspace paths."""
        return {key: str(value) for key, value in asdict(self).items()}


@dataclass(frozen=True, slots=True)
class BuildRequest:
    """Input options for a resumable B-matrix build."""

    from_stage: StageName = "bflow"
    to_stage: StageName = "dirac"
    manifest: Path | None = None
    start_valid_time: str | None = None
    end_valid_time: str | None = None
    valid_interval_hours: int = 24
    dt: int | None = None
    bflow_workspace: Path | None = None
    clean: bool = False
    skip_weights: bool = False
    poll_seconds: int = 30
    nicas_parallel: bool = False
    so_variant: str = "default"
    plot_level: int = 30
    plot_dpi: int = 150
    plot_variables: tuple[str, ...] = ()
    plots_workspace: Path | None = None
    dry_run: bool = False

    def __post_init__(self) -> None:
        if self.from_stage not in STAGES or self.to_stage not in STAGES:
            raise ConfigurationError(f"Etapas válidas: {', '.join(STAGES)}")
        if STAGES.index(self.from_stage) > STAGES.index(self.to_stage):
            raise ConfigurationError("from_stage deve preceder ou ser igual a to_stage.")


@dataclass(frozen=True, slots=True)
class PipelinePlan:
    """Dry-run plan exposing stages, inputs, workspaces and final products."""

    paths: PipelinePaths
    from_stage: StageName
    to_stage: StageName
    stages: tuple[StageName, ...]
    final_products: BMatrixProducts

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable plan."""
        return {
            "from_stage": self.from_stage,
            "to_stage": self.to_stage,
            "stages": list(self.stages),
            "workspaces": self.paths.as_strings(),
            "final_products": {key: str(value) for key, value in asdict(self.final_products).items()},
        }


def _pairs_from_request(config: Mapping[str, object], request: BuildRequest) -> tuple[list[BflowPair], Path]:
    if request.manifest:
        pairs = read_manifest(request.manifest)
        if not pairs:
            raise WorkflowError("Manifesto BFLOW/NMC não contém pares.")
        workspace = request.bflow_workspace or default_workspace(config, pairs[0].valid_time, pairs[-1].valid_time)
        return pairs, Path(workspace)
    if not request.start_valid_time or not request.end_valid_time:
        if request.bflow_workspace:
            return [], request.bflow_workspace
        raise ConfigurationError(
            "Informe --manifest ou --start-valid-time/--end-valid-time ao iniciar em BFLOW."
        )
    runtime = config.get("runtime", {})
    dt = request.dt or int(runtime.get("config_dt", 60)) if isinstance(runtime, Mapping) else request.dt or 60
    pairs = build_pairs_from_range(
        config,
        request.start_valid_time,
        request.end_valid_time,
        request.valid_interval_hours,
        int(dt),
    )
    workspace = request.bflow_workspace or default_workspace(config, request.start_valid_time, request.end_valid_time)
    return pairs, Path(workspace)


def plan(config: Mapping[str, object], request: BuildRequest) -> PipelinePlan:
    """Create a side-effect-free plan for a selected stage range."""
    _, bflow = _pairs_from_request(config, request)
    paths = PipelinePaths.from_bflow(config, bflow, plots=request.plots_workspace)
    selected = tuple(STAGES[STAGES.index(request.from_stage) : STAGES.index(request.to_stage) + 1])
    products = BMatrixProducts.from_workspaces(
        vbal_workspace=paths.vbal,
        hdiag_workspace=paths.hdiag,
        nicas_workspace=paths.nicas,
        dirac_workspace=paths.dirac,
    )
    return PipelinePlan(paths, request.from_stage, request.to_stage, selected, products)


def generate_weights(config: Mapping[str, object], workspace: str | Path, *, force: bool = False) -> tuple[Path, Path]:
    """Generate and validate the integrated ESMPy weight pair for a BFLOW workspace."""
    return generate_esmf_weights(config, workspace, force=force)


def build(config: Mapping[str, object], request: BuildRequest) -> PipelinePlan:
    """Execute a selected, dependency-ordered B-matrix stage range.

    The function always waits for submitted scheduler jobs before launching the
    dependent stage. It is therefore safe to use for the full calibration
    sequence, while ``dry_run`` returns a plan without touching the filesystem.
    """
    pipeline_plan = plan(config, request)
    if request.dry_run:
        return pipeline_plan

    paths = pipeline_plan.paths
    pairs, requested_bflow = _pairs_from_request(config, request)
    if requested_bflow.resolve() != paths.bflow:
        raise AssertionError("Inconsistência interna de workspace BFLOW.")

    for stage in pipeline_plan.stages:
        if stage == "bflow":
            active_pairs = pairs or read_manifest(paths.bflow / "manifest.tsv")
            prepare_bflow(config, active_pairs, paths.bflow, force=request.clean)
            run_bflow_pipeline(config, paths.bflow, active_pairs, clean_output=request.clean, skip_weights=request.skip_weights)
        elif stage == "vbal":
            prepare_vbal(config, paths.bflow, workspace=paths.vbal, clean=request.clean)
            submit_vbal(paths.vbal, wait=True, poll_seconds=request.poll_seconds)
            validate_vbal(paths.vbal)
        elif stage == "hdiag":
            prepare_hdiag(config, paths.vbal, workspace=paths.hdiag, clean=request.clean)
            submit_hdiag(paths.hdiag, wait=True, poll_seconds=request.poll_seconds)
            validate_hdiag(paths.hdiag)
        elif stage == "nicas":
            prepare_nicas(config, paths.hdiag, workspace=paths.nicas, clean=request.clean)
            submit_nicas(
                paths.nicas,
                wait=True,
                poll_seconds=request.poll_seconds,
                parallel=request.nicas_parallel,
            )
            validate_nicas(paths.nicas)
        elif stage == "so":
            prepare_so(
                config,
                paths.nicas,
                paths.hdiag,
                paths.vbal,
                workspace=paths.so,
                clean=request.clean,
                variant=request.so_variant,
            )
            submit_so(paths.so, wait=True, poll_seconds=request.poll_seconds, variant=request.so_variant)
            validate_so(paths.so, variant=request.so_variant)
        elif stage == "dirac":
            prepare_dirac(
                config,
                paths.nicas,
                paths.hdiag,
                paths.vbal,
                workspace=paths.dirac,
                clean=request.clean,
            )
            submit_dirac(paths.dirac, wait=True, poll_seconds=request.poll_seconds)
            validate_dirac(paths.dirac)
        elif stage == "plots":
            generate_plots(
                pipeline_plan.final_products,
                paths.plots,
                clean=request.clean,
                level=request.plot_level,
                dpi=request.plot_dpi,
                variables=request.plot_variables,
            )
            validate_plots(paths.plots)
        else:  # defensive: StageName is closed above
            raise AssertionError(stage)
    return pipeline_plan


def validate(config: Mapping[str, object], stage: StageName, paths: PipelinePaths, *, variant: str = "default") -> None:
    """Validate one completed stage without submitting or regenerating it."""
    if stage == "bflow":
        from .bflow_core.validate import validate_products as validate_bflow
        pairs = read_manifest(paths.bflow / "manifest.tsv")
        validate_bflow(config, paths.bflow, pairs, stage="full")
        validate_bflow(config, paths.bflow, pairs, stage="ptb")
    elif stage == "vbal":
        validate_vbal(paths.vbal)
    elif stage == "hdiag":
        validate_hdiag(paths.hdiag)
    elif stage == "nicas":
        validate_nicas(paths.nicas)
    elif stage == "so":
        validate_so(paths.so, variant=variant)
    elif stage == "dirac":
        validate_dirac(paths.dirac)
    elif stage == "plots":
        validate_plots(paths.plots)
    else:
        raise ConfigurationError(f"Etapa inválida: {stage}")
