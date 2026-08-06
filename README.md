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

## Quick start

Use a project area and a separate work area:

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

Install both repositories in the active Python environment:

```bash
python -m pip install --no-deps -e "$MPASWF_ROOT"
python -m pip install -e "$BMATRIX_ROOT"
```

Configure the paths used by the default JACI x1.10242 case:

```bash
export MONAN_JEDI_SOURCE=/path/to/projects/MONAN-JEDI
export MONAN_JEDI_INSTALL=/path/to/install/monan-jedi-mpas
export MONAN_JEDI_UNBALANCE_EXE=/path/to/mpasjedi_unbalance_ensemble.x

export MPAS_MESH_ROOT=/path/to/mpas_meshes
export MPAS_JEDI_STATIC_ROOT=/path/to/validated/x1.10242/static-files

export STACK_ROOT=/path/to/spack-stack
```

Load the MPAS-JEDI runtime and inspect the fully composed configuration:

```bash
cd "$BMATRIX_ROOT"
source scripts/load_jaci_env.sh

CONFIG=configs/jaci-x1.10242.yaml
mpas-bmatrix check-config --config "$CONFIG"
```

The default configuration is composed from:

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

Read [`docs/configuration.md`](docs/configuration.md) before changing paths or
scientific parameters.

Run from an existing BFLOW workspace:

```bash
BFLOW="$WORK_ROOT/bmatrix/bflow_preprocessing/np128_<START_VALID>_<END_VALID>"

PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --to-stage plots \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean \
  --poll-seconds 30
```

Run from a `mpaswf` forecast-pair manifest:

```bash
MANIFEST=/path/to/mpaswf-work/products/mpas-forecast-manifest.tsv

PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage plots \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean \
  --poll-seconds 30
```

## Documentation map

### User/operator documentation

| Document | Purpose |
| --- | --- |
| [`docs/end-to-end-tutorial.md`](docs/end-to-end-tutorial.md) | Full colleague smoke-test procedure. |
| [`docs/user-guide.md`](docs/user-guide.md) | Main execution guide: how to run, what to provide and how to validate. |
| [`docs/configuration.md`](docs/configuration.md) | Configuration hierarchy, environment variables, include rules and rebuild boundaries. |
| [`docs/jaci-quickstart.md`](docs/jaci-quickstart.md) | Compact JACI command sequence. |
| [`docs/stage-products.md`](docs/stage-products.md) | Inputs, outputs and acceptance criteria for every stage. |
| [`docs/mpaswf-pairs.md`](docs/mpaswf-pairs.md) | How to generate f024/f048 NMC forecast pairs with `mpaswf`. |
| [`docs/operations.md`](docs/operations.md) | Troubleshooting, validation commands and operational notes. |

### Scientific/developer documentation

| Document | Purpose |
| --- | --- |
| [`docs/bmatrix-theory.md`](docs/bmatrix-theory.md) | Scientific theory and meaning of each stage. |
| [`docs/scientific-contract.md`](docs/scientific-contract.md) | Variable names, aliases, SABER/BUMP blocks and invariants. |
| [`docs/configuration-audit.md`](docs/configuration-audit.md) | Audit of the original three configuration files. |
| [`docs/configuration-reorganization.md`](docs/configuration-reorganization.md) | Configuration corrections and final ownership model. |
| [`docs/developer-guide.md`](docs/developer-guide.md) | Developer workflow, extension rules and maintenance expectations. |
| [`docs/architecture.md`](docs/architecture.md) | Internal module architecture and stage lifecycle. |
| [`docs/testing.md`](docs/testing.md) | Unit, integration and JACI smoke testing guidance. |
| [`docs/diagnostics-and-plots.md`](docs/diagnostics-and-plots.md) | Diagnostic plotting outputs and style conventions. |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Top-level contribution checklist. |

## Development checks

```bash
cd "$BMATRIX_ROOT"
mkdir -p .pytest-tmp

TMPDIR="$BMATRIX_ROOT/.pytest-tmp" \
PYTHONPATH="src:${PYTHONPATH:-}" \
python -m pytest -p no:cacheprovider -q

python -m ruff check src/bmatrix tests

git diff --check
```
