# Documentation index

This directory documents `MPAS-BMatrix`, the INPE/MONAN static B-matrix workflow
repository for MPAS-JEDI/SABER/BUMP background-error covariance products used in
the MONAN atmospheric data-assimilation workflow. It works with MPAS-based model
states, but it is not an official NCAR MPAS repository.

The documentation is intentionally separated by audience:

```text
User/operator docs
  how to run, configure, validate and interpret the stage products

Scientific/developer docs
  theory, contracts, architecture, tests and extension rules
```

## User/operator documentation

Read these when your goal is to configure or run the pipeline and inspect its
products.

| Document | Purpose |
| --- | --- |
| [`end-to-end-tutorial.md`](end-to-end-tutorial.md) | Full smoke-test procedure from checkout/environment through final artifact checks. |
| [`user-guide.md`](user-guide.md) | Main user guide: installation, stage-by-stage execution and acceptance checks. |
| [`configuration.md`](configuration.md) | Configuration hierarchy, required environment variables, include rules and rebuild boundaries. |
| [`jaci-quickstart.md`](jaci-quickstart.md) | Compact JACI-oriented command sequence. |
| [`stage-products.md`](stage-products.md) | Inputs, outputs and acceptance criteria for each production stage. |
| [`mpaswf-pairs.md`](mpaswf-pairs.md) | How to generate f024/f048 MPAS NMC forecast pairs and the manifest with `mpaswf`. |
| [`operations.md`](operations.md) | Troubleshooting, validation commands and operational notes. |
| [`diagnostics-and-plots.md`](diagnostics-and-plots.md) | Plot products, visual diagnostics and style conventions. |

## Scientific/developer documentation

Read these when your goal is to change code, modify the scientific contract or
understand how the implementation works.

| Document | Purpose |
| --- | --- |
| [`bmatrix-theory.md`](bmatrix-theory.md) | Scientific meaning of the B-matrix and the covariance-training stages. |
| [`scientific-contract.md`](scientific-contract.md) | Variable names, aliases, SABER/BUMP blocks, `Control2Analysis`, in-memory VBAL/HDIAG and DIRAC invariants. |
| [`in-memory-vbal-hdiag.md`](in-memory-vbal-hdiag.md) | Migration rationale and A/B validation of the in-memory inverse-VBAL path. |
| [`developer-guide.md`](developer-guide.md) | Developer workflow, extension rules, rebuild rules and PR expectations. |
| [`architecture.md`](architecture.md) | Internal module architecture, configuration layers and stage lifecycle. |
| [`testing.md`](testing.md) | Unit, integration and JACI smoke testing strategy. |
| [`configuration-audit.md`](configuration-audit.md) | Analysis of how the original three configuration files were used and where they conflicted. |
| [`configuration-reorganization.md`](configuration-reorganization.md) | Final configuration ownership, split layout and corrections. |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | Top-level contribution checklist. |
| [`refactoring.md`](refactoring.md) | Historical notes from the refactored architecture. |

## Scope

The full operational order is:

```text
mpaswf -> BFLOW -> VBAL -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

`mpaswf` is external and produces the forecast-pair manifest. This repository
owns the stages starting at BFLOW:

```text
BFLOW -> VBAL -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

The inverse vertical-balance transform required by HDIAG is applied in memory by
`BUMP_VerticalBalance`; the production workflow does not materialize
`samplesUnbalanced`. The former `unbalance_core` remains temporarily available
only for controlled A/B regression tests.

The repository does not own GFS download, WPS/ungrib, MPAS initialization or
forecast integration. In the current operational chain those upstream products
are generated with `mpaswf`, then passed into `MPAS-BMatrix` as NMC pairs or an
already prepared BFLOW workspace.

## Recommended checkout layout

Use generic roots and adapt only the exports to your system:

```bash
export PROJECT_ROOT=/path/to/projects
export WORK_ROOT=/path/to/work/MPAS-BMatrix

mkdir -p "$PROJECT_ROOT" "$WORK_ROOT"
cd "$PROJECT_ROOT"

git clone https://github.com/joaogerd/MPAS-BMatrix.git
git clone https://github.com/joaogerd/mpaswf.git

export BMATRIX_ROOT="$PROJECT_ROOT/MPAS-BMatrix"
export MPASWF_ROOT="$PROJECT_ROOT/mpaswf"
```

## Current validated case

The global x1.10242 case is composed from:

```text
configs/jaci.yaml
configs/jaci-x1.10242.yaml
configs/bmatrix-x1.10242.yaml
configs/bmatrix/x1.10242/*.yaml
```

A typical BFLOW workspace path follows this pattern:

```text
$WORK_ROOT/bmatrix/bflow_preprocessing/np128_<START_VALID>_<END_VALID>
```

Use `mpas-bmatrix check-config` to inspect the fully merged mapping and the list
of source YAML files before launching a calibration.
