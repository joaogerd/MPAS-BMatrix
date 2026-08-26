# MPAS-BMatrix

`MPAS-BMatrix` is the INPE/MONAN Python orchestration repository for building,
validating and diagnosing static MPAS-JEDI/SABER/BUMP background-error
covariance products used by the MONAN atmospheric data-assimilation workflow.

MONAN currently uses MPAS-based model states in this workflow. This repository
therefore works with MPAS-JEDI/SABER/BUMP products, but it is not an official
NCAR MPAS repository.

The package exposes one public command:

```bash
mpas-bmatrix
```

## Scope

The repository starts at the **BFLOW** boundary. It assumes that MPAS forecasts
and same-valid-time NMC pairs already exist. In the current workflow, those
upstream pairs are generated with the external [`mpaswf`](https://github.com/joaogerd/mpaswf)
workflow.

```text
mpaswf -> BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

`mpaswf` owns GFS/WPS, MPAS initialization, MPAS forecasts and the forecast-pair
manifest. `MPAS-BMatrix` owns the covariance product contract, SABER/BUMP YAML
rendering, PBS orchestration, validation and diagnostics from BFLOW onward.

## What the B-matrix represents

In variational data assimilation, the background-error covariance matrix `B`
controls how observational information spreads horizontally, vertically, between
variables and with statistically estimated amplitude.

In MPAS-JEDI/SABER, the static B is represented by operators and files rather
than by one dense matrix:

```text
B ≈ C2A · VBAL · StdDev · NICAS · StdDev · VBALᵀ · C2Aᵀ
```

`UNBALANCE` is intentionally explicit in this repository: VBAL calibrates the
balance transform, UNBALANCE writes the unbalanced training members, and HDIAG
uses those members for the statistics.

## Quick start on JACI

Clone and install MPAS-BMatrix:

```bash
git clone https://github.com/joaogerd/MPAS-BMatrix.git
cd MPAS-BMatrix
python -m pip install -e .
```

Create the minimal user setup:

```bash
mpas-bmatrix setup --site jaci
```

The default workspace is:

```text
/p/projetos/monan_das/<USER>/work/MPAS-BMatrix
```

Use another persistent work area only when needed:

```bash
mpas-bmatrix setup --site jaci --workspace /path/to/work/MPAS-BMatrix
```

Validate software, mesh, static inputs and MPI partition before submitting jobs:

```bash
mpas-bmatrix doctor
```

Inspect exactly which paths were selected and what each one represents:

```bash
mpas-bmatrix paths
```

Inspect the composed configuration:

```bash
mpas-bmatrix check-config
```

For the complete machine-readable configuration:

```bash
mpas-bmatrix check-config --json
```

The normal JACI onboarding does **not** require the user to start by declaring a
list of opaque `/path/to/...` variables. Explicit environment variables remain
available as advanced overrides for non-standard installations.

Read [`docs/getting-started.md`](docs/getting-started.md) for the first-run model,
resource meanings, discovery order and expected workspace layout.

## Configuration model

The default x1.10242 configuration is internally composed from:

```text
configs/jaci.yaml
  JACI site/build/runtime base

configs/jaci-x1.10242.yaml
  runnable x1.10242 case

configs/bmatrix-x1.10242.yaml
  scientific-contract aggregator

configs/bmatrix/x1.10242/*.yaml
  one documented scientific fragment per stage
```

This hierarchy remains important for developers and scientific audit, but normal
users should not need to edit these files for a standard JACI run.

## Running the B-matrix workflow

From an existing BFLOW workspace:

```bash
mpas-bmatrix build \
  --config configs/jaci-x1.10242.yaml \
  --bflow-workspace /path/to/BFLOW_WORKSPACE \
  --from-stage vbal \
  --to-stage plots \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean \
  --poll-seconds 30
```

From an `mpaswf` forecast-pair manifest:

```bash
mpas-bmatrix build \
  --config configs/jaci-x1.10242.yaml \
  --manifest /path/to/mpas-forecast-manifest.tsv \
  --from-stage bflow \
  --to-stage plots \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean \
  --poll-seconds 30
```

Use `--dry-run` to inspect the planned stage range and deterministic workspaces
without creating files or submitting PBS jobs.

## Documentation map

### User/operator documentation

| Document | Purpose |
| --- | --- |
| [`docs/getting-started.md`](docs/getting-started.md) | Recommended first run on JACI; setup, discovery, doctor and path meanings. |
| [`docs/end-to-end-tutorial.md`](docs/end-to-end-tutorial.md) | Full colleague smoke-test procedure. |
| [`docs/user-guide.md`](docs/user-guide.md) | Main execution guide: how to run, what to provide and how to validate. |
| [`docs/configuration.md`](docs/configuration.md) | Configuration hierarchy, overrides, include rules and rebuild boundaries. |
| [`docs/jaci-quickstart.md`](docs/jaci-quickstart.md) | Compact JACI command sequence. |
| [`docs/stage-products.md`](docs/stage-products.md) | Inputs, outputs and acceptance criteria for every stage. |
| [`docs/mpaswf-pairs.md`](docs/mpaswf-pairs.md) | How to generate f024/f048 NMC forecast pairs with `mpaswf`. |
| [`docs/operations.md`](docs/operations.md) | Troubleshooting, validation commands and operational notes. |

### Scientific/developer documentation

| Document | Purpose |
| --- | --- |
| [`docs/bmatrix-theory.md`](docs/bmatrix-theory.md) | Scientific theory and meaning of each stage. |
| [`docs/scientific-contract.md`](docs/scientific-contract.md) | Variable names, aliases, SABER/BUMP blocks and invariants. |
| [`docs/configuration-audit.md`](docs/configuration-audit.md) | Audit of the original configuration files. |
| [`docs/configuration-reorganization.md`](docs/configuration-reorganization.md) | Configuration corrections and ownership model. |
| [`docs/developer-guide.md`](docs/developer-guide.md) | Developer workflow, extension rules and maintenance expectations. |
| [`docs/architecture.md`](docs/architecture.md) | Internal module architecture and stage lifecycle. |
| [`docs/testing.md`](docs/testing.md) | Unit, integration and JACI smoke testing guidance. |
| [`docs/diagnostics-and-plots.md`](docs/diagnostics-and-plots.md) | Diagnostic plotting outputs and style conventions. |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Top-level contribution checklist. |

## Development checks

Developer workflows may use the module entry point and explicit `PYTHONPATH`.
Normal user documentation should use only the installed `mpas-bmatrix` command.

```bash
cd /path/to/MPAS-BMatrix
mkdir -p .pytest-tmp

TMPDIR="$PWD/.pytest-tmp" \
PYTHONPATH="src:${PYTHONPATH:-}" \
python -m pytest -p no:cacheprovider -q

python -m ruff check src/bmatrix tests

git diff --check
```
