# MPAS-BMatrix

`MPAS-BMatrix` is the official Python orchestration repository for building,
validating and diagnosing static MPAS-JEDI/SABER/BUMP background-error
covariance products for a global MPAS workflow.

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

Use a project area and a separate work area. Adapt only the exported roots:

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

On JACI, load the MPAS-JEDI runtime:

```bash
cd "$BMATRIX_ROOT"
export STACK_ROOT=/path/to/spack-stack
source scripts/load_jaci_env.sh
```

Run from an existing BFLOW workspace:

```bash
cd "$BMATRIX_ROOT"

CONFIG=configs/jaci-x1.10242.yaml
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

The documentation is separated by audience.

### User/operator documentation

| Document | Purpose |
| --- | --- |
| [`docs/user-guide.md`](docs/user-guide.md) | Main execution guide: how to run, what to provide and how to validate. |
| [`docs/jaci-quickstart.md`](docs/jaci-quickstart.md) | Compact JACI command sequence. |
| [`docs/stage-products.md`](docs/stage-products.md) | Inputs, outputs and acceptance criteria for every stage. |
| [`docs/mpaswf-pairs.md`](docs/mpaswf-pairs.md) | How to generate f024/f048 NMC forecast pairs with `mpaswf`. |
| [`docs/operations.md`](docs/operations.md) | Troubleshooting, validation commands and operational notes. |

### Scientific/developer documentation

| Document | Purpose |
| --- | --- |
| [`docs/bmatrix-theory.md`](docs/bmatrix-theory.md) | Scientific theory and meaning of each stage. |
| [`docs/scientific-contract.md`](docs/scientific-contract.md) | Variable names, aliases, SABER/BUMP blocks and invariants. |
| [`docs/developer-guide.md`](docs/developer-guide.md) | Developer workflow, extension rules and maintenance expectations. |
| [`docs/architecture.md`](docs/architecture.md) | Internal module architecture and stage lifecycle. |
| [`docs/testing.md`](docs/testing.md) | Unit, integration and JACI smoke testing guidance. |
| [`docs/diagnostics-and-plots.md`](docs/diagnostics-and-plots.md) | Diagnostic plotting outputs and style conventions. |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Top-level contribution checklist. |

## Development checks

For documentation or code changes:

```bash
cd "$BMATRIX_ROOT"
mkdir -p .pytest-tmp

TMPDIR="$BMATRIX_ROOT/.pytest-tmp" \
PYTHONPATH="src:${PYTHONPATH:-}" \
python -m pytest -p no:cacheprovider -q

python -m ruff check src/bmatrix tests

git diff --check
```
