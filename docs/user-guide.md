# User Guide

This guide is for users who need to run the MPAS-JEDI static B-matrix workflow,
check the products, and understand whether each stage completed correctly.

It deliberately avoids implementation details. For code architecture, tests and
scientific formulas, read [`developer-guide.md`](developer-guide.md),
[`architecture.md`](architecture.md), [`testing.md`](testing.md) and
[`bmatrix-theory.md`](bmatrix-theory.md).

## 1. What this repository does

`MPAS-BMatrix` builds, validates and diagnoses the static MPAS-JEDI/SABER/BUMP
background-error covariance product set for a global MPAS workflow.

The end-to-end operational chain is sequential:

```text
mpaswf -> BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

The ordering is part of the scientific contract. Later stages consume products
from earlier stages, so a subtle failure in one stage can propagate downstream.
Do not skip validation between stages when debugging.

## 2. Scope boundary

The upstream MPAS forecast production is handled outside this repository, usually
by `mpaswf`:

```text
mpaswf
  -> GFS/WPS/ungrib
  -> mpas_init_atmosphere
  -> MPAS forecasts f024/f048
  -> same-valid-time NMC forecast-pair manifest
```

`MPAS-BMatrix` starts at BFLOW:

```text
MPAS-BMatrix
  -> BFLOW
  -> VBAL
  -> UNBALANCE
  -> HDIAG
  -> NICAS
  -> SO
  -> DIRAC
  -> PLOTS
```

## 3. Clone and install

Use generic roots and adapt only the exported paths:

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

Install the Python packages in the active environment:

```bash
python -m pip install --no-deps -e "$MPASWF_ROOT"
python -m pip install -e "$BMATRIX_ROOT"
```

Optional extras:

```bash
cd "$BMATRIX_ROOT"
python -m pip install -e ".[weights,bflow,diagnostics]"
```

## 4. Load the runtime environment

On JACI, load the MPAS-JEDI runtime from the repository-local loader:

```bash
cd "$BMATRIX_ROOT"
export STACK_ROOT=/path/to/spack-stack
source scripts/load_jaci_env.sh
```

Set the common variables:

```bash
CONFIG=configs/jaci-x1.10242.yaml
```

For an already prepared BFLOW workspace:

```bash
BFLOW="$WORK_ROOT/bmatrix/bflow_preprocessing/np128_<START_VALID>_<END_VALID>"
```

For a fresh run from `mpaswf` products:

```bash
MANIFEST=/path/to/mpaswf-work/products/mpas-forecast-manifest.tsv
```

## 5. Quick start

### Build from an existing BFLOW workspace

```bash
cd "$BMATRIX_ROOT"

PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --to-stage plots \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean \
  --poll-seconds 30
```

### Build from a `mpaswf` manifest

```bash
cd "$BMATRIX_ROOT"

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

### Generate only plots from completed products

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix plots \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean
```

## 6. Inputs and configuration files

The main configuration files are:

```text
configs/jaci-x1.10242.yaml
configs/bmatrix-x1.10242.yaml
```

`configs/jaci-x1.10242.yaml` is the platform/runtime configuration. It defines
paths, mesh, partitioning, PBS resources, executables and environment settings.

`configs/bmatrix-x1.10242.yaml` is the scientific contract. It defines control
variables, aliases, VBAL relations, HDIAG parameters, NICAS parameters, SO
settings, DIRAC settings and plotting defaults.

Before changing scientific parameters, read
[`scientific-contract.md`](scientific-contract.md). Scientific changes usually
require rebuilding downstream stages.

## 7. User workflow by stage

Each stage below follows the same structure:

```text
Input -> what the stage does -> how to run -> outputs -> acceptance criteria
```

A compact product table is also available in
[`stage-products.md`](stage-products.md).

### 7.1 mpaswf: upstream forecast-pair generation

**Input**

- MPAS mesh/static configuration;
- GFS/WPS inputs or equivalent atmospheric initial conditions;
- `mpaswf` configuration.

**What it does**

Runs the external MPAS forecast workflow and creates same-valid-time f048/f024
forecast pairs for the NMC method.

**How to run**

```bash
cd "$MPASWF_ROOT"
MPASWF_CONFIG=/path/to/mpaswf-config.yaml

mpaswf run --phase prepare  --config "$MPASWF_CONFIG"
mpaswf run --phase init     --config "$MPASWF_CONFIG" --submit --wait
mpaswf run --phase forecast --config "$MPASWF_CONFIG" --submit --wait
mpaswf run --phase manifest --config "$MPASWF_CONFIG"
```

**Outputs**

```text
<mpaswf work_dir>/products/mpas-forecast-manifest.tsv
```

**Acceptance criteria**

- the manifest exists;
- each row has f048 and f024 states for the same valid time;
- the referenced forecast files exist and are readable.

### 7.2 BFLOW: prepare B-matrix perturbations

**Input**

- `mpaswf` forecast-pair manifest, or an existing BFLOW workspace;
- MPAS mesh/static files;
- scientific configuration from `configs/bmatrix-x1.10242.yaml`.

**What it does**

Transforms forecast pairs into the products used by covariance calibration,
including the NMC perturbation `PTB_f48mf24.nc`.

**How to run**

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage bflow \
  --clean \
  --poll-seconds 30
```

**Outputs**

```text
FULL_f24.nc
FULL_f48.nc
PTB_f48mf24.nc
template_PTB.nc
manifest.tsv
ESMF_weights/weights_manifest.json
```

**Acceptance criteria**

- `manifest.tsv` exists in the BFLOW workspace;
- each expected member directory exists;
- `FULL_f24.nc`, `FULL_f48.nc` and `PTB_f48mf24.nc` exist for each member;
- the perturbation files contain the expected control variables;
- ESMF weight metadata exists when regridding is performed.

### 7.3 VBAL: calibrate vertical and multivariate balance

**Input**

- BFLOW workspace;
- `PTB_f48mf24.nc` members;
- background/template state and static files.

**What it does**

Calibrates the vertical/multivariate balance operator. Conceptually, it estimates
how perturbations associated with streamfunction explain balanced components of
velocity potential, temperature and surface pressure.

**How to run**

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage vbal \
  --to-stage vbal \
  --clean \
  --poll-seconds 30
```

**Outputs**

```text
VBAL/mpas_vbal.nc
VBAL/mpas_sampling.nc
VBAL/mpas_vbal_local_*
VBAL/mpas_sampling_local_*
samples/PTB_f48mf24_*.nc
```

**Acceptance criteria**

- the PBS job finishes successfully;
- `run_vbal.runlog` reports successful completion;
- `mpas_vbal.nc` and `mpas_sampling.nc` exist;
- local VBAL and sampling products exist for the expected MPI ranks;
- the staged `samples/PTB_f48mf24_*.nc` files exist and are CDF5 when required.

### 7.4 UNBALANCE: materialize unbalanced training members

**Input**

- VBAL products;
- centered/staged perturbation samples.

**What it does**

Applies the inverse/removal of the balanced part represented by the VBAL
operator and writes explicit unbalanced perturbation members for HDIAG.

This stage is intentionally explicit. Do not rely on VBAL calibration alone to
write the final `samplesUnbalanced` members.

**How to run**

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage unbalance \
  --to-stage unbalance \
  --clean \
  --poll-seconds 30
```

**Outputs**

```text
samplesUnbalanced/PTB_f48mf24_001.nc
samplesUnbalanced/PTB_f48mf24_002.nc
samplesUnbalanced/PTB_f48mf24_003.nc
samplesUnbalanced/PTB_f48mf24_004.nc
```

**Acceptance criteria**

- all expected unbalanced members exist;
- files are readable NetCDF products;
- the files contain the expected control variables;
- member count is sufficient for HDIAG;
- validation passes before running HDIAG.

### 7.5 HDIAG: compute standard deviations and correlation scales

**Input**

- `samplesUnbalanced/PTB_f48mf24_*.nc`;
- VBAL products;
- background/static files.

**What it does**

Computes the statistical diagnostics used by the rest of the static B:
standard deviation, horizontal correlation scales and vertical correlation
scales.

**How to run**

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage hdiag \
  --to-stage hdiag \
  --clean \
  --poll-seconds 30
```

**Outputs**

```text
HDIAG/mpas.stddev.nc
HDIAG/mpas.cor_rh.nc
HDIAG/mpas.cor_rv.nc
```

**Acceptance criteria**

- the PBS job finishes successfully;
- all three products exist;
- products are readable and have dimensions consistent with the mesh/control variables;
- values are not entirely missing or trivially zero;
- no BUMP radius/sampling errors appear in the run log.

### 7.6 NICAS: build correlation/localization products

**Input**

- HDIAG products: `mpas.cor_rh.nc`, `mpas.cor_rv.nc`, `mpas.stddev.nc`;
- static files and background inherited from previous stages.

**What it does**

Builds the NICAS spatial correlation/localization products, usually per control
variable, then merges them into a single product set used by SO, DIRAC and later
assimilation runs.

**How to run**

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage nicas \
  --to-stage nicas \
  --clean \
  --poll-seconds 30
```

**Outputs**

```text
NICAS/merge/mpas_nicas.nc
NICAS/merge/mpas_nicas_local_*
NICAS/merge/mpas_nicas_grids_local_*
NICAS/merge/mpas.nicas_norm.nc
NICAS/merge/mpas.dirac_nicas.nc
NICAS/merge/merge.done
```

**Acceptance criteria**

- per-variable NICAS jobs finish successfully;
- the merge step finishes successfully;
- `merge.done` exists;
- global, local and grid products exist;
- `surface_pressure` remains handled as a 2D control and is not forced into the
  3D NICAS read grid.

### 7.7 SO: single-observation variational validation

**Input**

- merged NICAS products;
- HDIAG standard deviation;
- VBAL products;
- enriched MPAS background state.

**What it does**

Runs a small variational single-observation test to confirm that the complete B
composition can be read and applied by `mpasjedi_variational.x`.

**How to run**

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage so \
  --to-stage so \
  --clean \
  --poll-seconds 30
```

**Outputs**

```text
SO/obsout_SO_T.h5
SO/obsout_SO_U.h5
SO/an.*.nc
SO/run_SO.runlog
```

**Acceptance criteria**

- `run_SO.runlog` ends with successful OOPS status;
- the log contains `CostFunction::addIncrement: Analysis`;
- expected `obsout_SO_*.h5` files exist;
- an MPAS-native `an.*.nc` file exists and is readable;
- do not treat zero difference in native MPAS output fields as an automatic
  failure without checking the OOPS/JEDI response.

### 7.8 DIRAC: complete-B impulse response

**Input**

- merged NICAS products;
- HDIAG standard deviation;
- VBAL products;
- background/static files.

**What it does**

Applies an impulse in a selected variable/location and writes the spatial and
vertical response of the complete B.

**How to run**

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage dirac \
  --to-stage dirac \
  --clean \
  --poll-seconds 30
```

**Outputs**

```text
DIRAC/mpas.dirac.nc
```

**Acceptance criteria**

- the PBS job finishes successfully;
- `mpas.dirac.nc` exists and is readable;
- the response is not entirely missing or trivially zero;
- DIRAC uses the maintained full `dirLats`/`dirLons` plus singular selector
  contract.

### 7.9 PLOTS: diagnostic figures

**Input**

- completed products from HDIAG, VBAL, NICAS and DIRAC.

**What it does**

Generates visual diagnostics and a summary table. It does not alter scientific
products and does not submit PBS jobs.

**How to run**

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix plots \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean
```

**Outputs**

```text
PLOTS/summary.csv
PLOTS/README.md
PLOTS/01_stddev/
PLOTS/02_corr_horizontal/
PLOTS/03_corr_vertical/
PLOTS/04_vbal/
PLOTS/05_dirac/
PLOTS/06_spatial_fields/
```

**Acceptance criteria**

- `summary.csv` exists;
- expected plot directories exist;
- figures are generated for available products;
- maps and colorbars are readable;
- near-zero fields are interpreted cautiously and checked against logs/products.

## 8. Validation commands

Validate a completed stage:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix validate \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --stage <stage>
```

List products:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix products \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW"
```

Check NetCDF kind when CDF5 is required:

```bash
ncdump -k <file.nc>
```

## 9. Troubleshooting

Common issues and fixes are maintained in [`operations.md`](operations.md).

Start with these checks:

```bash
# Check stage logs.
find "$WORK_ROOT" -name '*.runlog' -o -name 'stdout.log' -o -name 'stderr.log'

# Check NetCDF format.
ncdump -k <file.nc>

# Check whether expected products exist.
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix products \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW"
```

Avoid persistent logs under `/tmp`. Use a durable work directory:

```bash
AUDIT_DIR="$WORK_ROOT/audits"
mkdir -p "$AUDIT_DIR"
```
