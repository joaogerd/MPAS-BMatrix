# Documentation index

This directory documents `MPAS-BMatrix`, the official MPAS-JEDI/SABER/BUMP
static B-matrix workflow repository.

The documentation is intentionally separated by audience:

```text
User/operator docs
  how to run, what to provide, what each stage produces and how to validate

Scientific/developer docs
  theory, contracts, architecture, tests and extension rules
```

## User/operator documentation

Read these when your goal is to run the pipeline or inspect products.

| Document | Purpose |
| --- | --- |
| [`user-guide.md`](user-guide.md) | Main user guide: installation, quick start, stage-by-stage execution and acceptance checks. |
| [`jaci-quickstart.md`](jaci-quickstart.md) | Compact JACI-oriented command sequence. |
| [`stage-products.md`](stage-products.md) | Inputs, outputs and acceptance criteria for each stage. |
| [`mpaswf-pairs.md`](mpaswf-pairs.md) | How to generate f024/f048 MPAS NMC forecast pairs and the manifest with `mpaswf`. |
| [`operations.md`](operations.md) | Troubleshooting, validation commands and operational notes. |
| [`diagnostics-and-plots.md`](diagnostics-and-plots.md) | Plot products, visual diagnostics and style conventions. |

## Scientific/developer documentation

Read these when your goal is to change code, modify the scientific contract or
understand how the implementation works.

| Document | Purpose |
| --- | --- |
| [`bmatrix-theory.md`](bmatrix-theory.md) | Scientific meaning of the B-matrix and each workflow stage, including explicit UNBALANCE. |
| [`scientific-contract.md`](scientific-contract.md) | Variable names, aliases, SABER/BUMP blocks, `Control2Analysis`, UNBALANCE and DIRAC invariants. |
| [`developer-guide.md`](developer-guide.md) | Developer workflow, extension rules, rebuild rules and PR expectations. |
| [`architecture.md`](architecture.md) | Internal module architecture, configuration layers and stage lifecycle. |
| [`testing.md`](testing.md) | Unit, integration and JACI smoke testing strategy. |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | Top-level contribution checklist. |
| [`refactoring.md`](refactoring.md) | Historical notes from the refactored architecture. |

## Scope

The full operational order is:

```text
mpaswf -> BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

`mpaswf` is external and produces the forecast-pair manifest. This repository
owns the stages starting at BFLOW:

```text
BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

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

The documentation assumes the global MPAS tutorial mesh and the scientific
contract declared in:

```text
configs/jaci-x1.10242.yaml
configs/bmatrix-x1.10242.yaml
```

A typical BFLOW workspace path follows this pattern:

```text
$WORK_ROOT/bmatrix/bflow_preprocessing/np128_<START_VALID>_<END_VALID>
```

Use the same stage contract when comparing outputs or debugging regressions.
