# User Guide

This guide is for users who need to configure, run and validate the INPE/MONAN
static B-matrix workflow without reading the Python implementation.

For scientific theory, code architecture and extension rules, read:

- [`bmatrix-theory.md`](bmatrix-theory.md)
- [`scientific-contract.md`](scientific-contract.md)
- [`developer-guide.md`](developer-guide.md)
- [`architecture.md`](architecture.md)

## 1. Workflow and scope

The complete operational chain is sequential:

```text
mpaswf -> BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

`mpaswf` is an external upstream workflow. It owns GFS/WPS, MPAS initialization,
MPAS f024/f048 forecasts and the same-valid-time forecast-pair manifest.

`MPAS-BMatrix` starts at BFLOW and owns the covariance calibration, validation
and diagnostics. The order is critical: a stage consumes products from earlier
stages, and a configuration change invalidates that stage and all downstream
products.

## 2. Clone and install

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

Install both packages in the active Python environment:

```bash
python -m pip install --no-deps -e "$MPASWF_ROOT"
python -m pip install -e "$BMATRIX_ROOT"
```

Optional MPAS-BMatrix extras:

```bash
cd "$BMATRIX_ROOT"
python -m pip install -e ".[weights,bflow,diagnostics]"
```

## 3. Configure the JACI x1.10242 case

The default runnable case uses one MONAN-JEDI runtime installation root plus
separate mesh/case data paths:

```bash
export MONAN_JEDI_INSTALL_ROOT=/p/projetos/monan_das/$USER/build/monan-jedi

export MPAS_MESH_ROOT=/path/to/mpas_meshes
export MPAS_JEDI_STATIC_ROOT=/path/to/validated/x1.10242/static-files

export STACK_ROOT=/path/to/spack-stack
```

From `MONAN_JEDI_INSTALL_ROOT`, MPAS-BMatrix derives the required JEDI/SABER
executables from `bin/`, MPAS runtime tables from `share/MPAS/core_atmosphere`,
and `geovars.yaml` / `keptvars.yaml` from
`share/monan-jedi/mpas-jedi/namelists/`. A MONAN-JEDI source checkout and a
separate `MONAN_JEDI_UNBALANCE_EXE` are not required for normal use.

For backward compatibility, `MONAN_JEDI_INSTALL` is still accepted when the
canonical `MONAN_JEDI_INSTALL_ROOT` variable is not set.

`MPAS_JEDI_STATIC_ROOT` must contain the compatible x1.10242 invariant,
namelist, streams and stream-list files. These files must match the installed
MPAS Registry and physics tables.

Load the runtime:

```bash
cd "$BMATRIX_ROOT"
source scripts/load_jaci_env.sh
```

The configuration is composed from four layers:

```text
configs/jaci.yaml
  JACI site/build/runtime settings

configs/jaci-x1.10242.yaml
  mesh and static inputs for the runnable case

configs/bmatrix-x1.10242.yaml
  short scientific-contract aggregator

configs/bmatrix/x1.10242/*.yaml
  one documented fragment per scientific stage
```

Set and inspect the runnable configuration:

```bash
CONFIG=configs/jaci-x1.10242.yaml
mpas-bmatrix check-config --config "$CONFIG"
```

Do not start a long PBS sequence until `check-config` shows the expected paths,
MPI size, stage sections and source files. See
[`configuration.md`](configuration.md) for every variable, include rules and
rebuild boundaries.

## 4. Prepare the forecast-pair input

### Option A: use a `mpaswf` manifest

Generate the f048/f024 forecasts and manifest with `mpaswf`. The final input to
MPAS-BMatrix is typically:

```bash
MANIFEST=/path/to/mpaswf-work/products/mpas-forecast-manifest.tsv
```

Each row must reference an f048 and f024 MPAS state valid at the same time. See
[`mpaswf-pairs.md`](mpaswf-pairs.md).

### Option B: resume from an existing BFLOW workspace

```bash
BFLOW="$WORK_ROOT/bmatrix/bflow_preprocessing/np128_<START_VALID>_<END_VALID>"
```

The workspace must already contain a valid `manifest.tsv` and completed BFLOW
products.

## 5. Dry-run and full execution

Inspect the stage plan without creating files or submitting jobs:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --to-stage plots \
  --dry-run
```

Run the complete BFLOW-to-PLOTS workflow:

```bash
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

Resume from an existing BFLOW workspace:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage vbal \
  --to-stage plots \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean \
  --poll-seconds 30
```

## 6. Run and validate one stage

Use the same stage name in `--from-stage` and `--to-stage`:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage hdiag \
  --to-stage hdiag \
  --clean \
  --poll-seconds 30
```

Validate a completed stage without rerunning it:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix validate \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --stage hdiag
```

Valid stage names are:

```text
bflow, vbal, unbalance, hdiag, nicas, so, dirac, plots
```

## 7. Stage-by-stage product checks

The detailed file matrix is in [`stage-products.md`](stage-products.md). The
minimum user checks are summarized below.

### BFLOW

**Input:** same-valid-time f048/f024 forecast pairs.

**Purpose:** transform MPAS forecasts into FULL states and NMC perturbations.

**Main outputs:**

```text
FULL_f48.nc
FULL_f24.nc
PTB_f48mf24.nc
template_PTB.nc
manifest.tsv
ESMF_weights/weights_manifest.json
```

**Accept when:** every manifest member has readable FULL/PTB files containing the
required control variables and expected dimensions.

### VBAL

**Input:** BFLOW perturbations.

**Purpose:** calibrate vertical/multivariate balance coefficients and sampling.

**Main outputs:**

```text
VBAL/mpas_vbal.nc
VBAL/mpas_sampling.nc
VBAL/mpas_vbal_local_*
VBAL/mpas_sampling_local_*
```

**Accept when:** the PBS job succeeds and all global/local products exist for the
configured MPI ranks.

### UNBALANCE

**Input:** VBAL products and centered perturbation samples.

**Purpose:** apply K2^-1 and explicitly write the unbalanced ensemble used by
HDIAG.

**Main outputs:**

```text
samplesUnbalanced/PTB_f48mf24_*.nc
```

**Accept when:** the expected member count exists, files are readable/CDF5 when
required and all declared controls are present.

### HDIAG

**Input:** `samplesUnbalanced`.

**Purpose:** estimate standard deviations and horizontal/vertical correlation
scales.

**Main outputs:**

```text
HDIAG/mpas.stddev.nc
HDIAG/mpas.cor_rh.nc
HDIAG/mpas.cor_rv.nc
```

**Accept when:** all products exist, dimensions are consistent and fields are not
entirely missing or trivially zero.

### NICAS

**Input:** HDIAG correlation products.

**Purpose:** build and merge the compressed spatial correlation operator.

**Main outputs:**

```text
NICAS/merge/mpas_nicas.nc
NICAS/merge/mpas_nicas_local_*
NICAS/merge/mpas_nicas_grids_local_*
NICAS/merge/mpas.nicas_norm.nc
NICAS/merge/mpas.dirac_nicas.nc
NICAS/merge/merge.done
```

**Accept when:** every per-control job and the merge succeed, and 2D surface
pressure remains separate from the 3D local read grid.

### SO

**Input:** calibrated NICAS, standard deviation and VBAL products.

**Purpose:** verify the complete B in a small variational single-observation run.

**Main outputs:**

```text
SO/an.*.nc
SO/obsout_SO_T.h5
SO/obsout_SO_U.h5
SO/run_SO.runlog
```

**Accept when:** OOPS finishes with status 0, the log contains
`CostFunction::addIncrement: Analysis`, and expected analysis/observation files
exist. A zero difference in MPAS-native output fields is not, by itself, proof
of failure.

### DIRAC

**Input:** calibrated complete B.

**Purpose:** write the complete-B response to one configured impulse.

**Main output:**

```text
DIRAC/mpas.dirac.nc
```

**Accept when:** the toolbox job succeeds and the response is readable and
nontrivial.

### PLOTS

**Input:** completed scientific products.

**Purpose:** generate diagnostic figures and summary tables without changing the
B products.

**Main outputs:**

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

**Accept when:** `summary.csv` and the expected figure directories exist and the
plots are physically interpretable.

## 8. Configuration changes and reruns

Start from the earliest affected stage and include `--clean`:

```text
controls or BFLOW changed
  -> rerun from BFLOW

VBAL changed
  -> rerun from VBAL

HDIAG changed
  -> rerun from HDIAG

NICAS changed
  -> rerun from NICAS

SO observation/minimizer changed
  -> rerun SO

SO analysis-variable list changed
  -> rerun SO and DIRAC

DIRAC point/variable changed
  -> rerun DIRAC and PLOTS
```

Never reuse downstream products after changing an upstream scientific contract.

## 9. Troubleshooting sequence

When a stage fails:

1. stop the pipeline at the failed stage;
2. inspect the generated YAML and PBS script in that stage workspace;
3. inspect `stdout.log`, `stderr.log` and the stage runlog;
4. run `mpas-bmatrix validate --stage <stage>`;
5. compare the resolved configuration with `check-config`;
6. verify every required upstream product before retrying;
7. rerun only from the earliest invalid stage with `--clean`.

See [`operations.md`](operations.md) for known errors such as BUMP universe-radius
limits, NICAS `nl0` mismatches, alias problems and MPAS stream-field errors.

## 10. Reproducibility record

For each test or production run, record:

```text
repository commit
configuration entry point
configuration_sources
bmatrix_contract_sources
mpaswf manifest or BFLOW workspace
stage range
PBS job IDs
main log path
final product paths
validation result
```

The end-to-end colleague test template is available in
[`end-to-end-tutorial.md`](end-to-end-tutorial.md).
