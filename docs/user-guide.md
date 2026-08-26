# User Guide

This guide is for users who need to configure, run and validate the INPE/MONAN
static B-matrix workflow without reading the Python implementation.

For the first run on JACI, start with [`getting-started.md`](getting-started.md).
For scientific theory and developer details, read:

- [`bmatrix-theory.md`](bmatrix-theory.md)
- [`scientific-contract.md`](scientific-contract.md)
- [`developer-guide.md`](developer-guide.md)
- [`architecture.md`](architecture.md)

## 1. Workflow and scope

The complete operational chain is sequential:

```text
mpaswf -> BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

`mpaswf` is the upstream workflow. It owns GFS/WPS, MPAS initialization, MPAS
f024/f048 forecasts and the same-valid-time forecast-pair manifest.

`MPAS-BMatrix` starts at BFLOW and owns covariance calibration, validation and
diagnostics. The order is critical: each stage consumes products from earlier
stages, and changing an upstream scientific contract invalidates downstream
products.

## 2. Install and configure the user workspace

Clone and install:

```bash
git clone https://github.com/joaogerd/MPAS-BMatrix.git
cd MPAS-BMatrix
python -m pip install -e .
```

Optional extras:

```bash
python -m pip install -e ".[weights,bflow,diagnostics]"
```

On JACI, configure only the user/site choice:

```bash
mpas-bmatrix setup --site jaci
```

The default work root is:

```text
/p/projetos/monan_das/<USER>/work/MPAS-BMatrix
```

Use another persistent area only when needed:

```bash
mpas-bmatrix setup --site jaci --workspace /path/to/work/MPAS-BMatrix
```

The normal workflow does not begin by asking the user to define every software,
mesh and static-data path. The CLI resolves known JACI resources and preserves
explicit environment variables only as advanced overrides.

## 3. Validate the runtime before submitting jobs

Run:

```bash
mpas-bmatrix doctor
```

`doctor` verifies the concrete resources required by the default x1.10242 case,
including the MPAS-JEDI/SABER installation, covariance/variational/unbalance
executables, mesh, graph, `np128` partition, invariant, namelist, streams, stream
lists, MPAS physics tables, `geovars.yaml`, `keptvars.yaml` and spack-stack root.

Do not start a long PBS sequence until the command ends with:

```text
READY
```

To understand exactly what was selected:

```bash
mpas-bmatrix paths
```

The output includes both each resolved path and its role. It also reports whether
a root came from an explicit environment override, automatic discovery, a site
default, the saved user setup or the package itself.

## 4. Inspect the composed configuration

The default case is composed internally from:

```text
configs/jaci.yaml
configs/jaci-x1.10242.yaml
configs/bmatrix-x1.10242.yaml
configs/bmatrix/x1.10242/*.yaml
```

Normal users do not need to edit these files for a standard JACI run.

Use:

```bash
mpas-bmatrix check-config
```

for the operator summary, and:

```bash
mpas-bmatrix check-config --json
```

for the complete resolved configuration used for debugging, audit or
reproducibility.

See [`configuration.md`](configuration.md) for path meanings, discovery rules,
advanced overrides, include semantics and rebuild boundaries.

## 5. Prepare the forecast-pair input

### Option A: use an `mpaswf` manifest

Generate the f048/f024 forecasts and manifest with `mpaswf`. The final input to
MPAS-BMatrix is typically:

```bash
MANIFEST=/path/to/mpaswf-work/products/mpas-forecast-manifest.tsv
```

Each row must reference an f048 and f024 MPAS state valid at the same time. See
[`mpaswf-pairs.md`](mpaswf-pairs.md).

### Option B: resume from an existing BFLOW workspace

Use an already completed BFLOW workspace:

```bash
BFLOW=/path/to/bflow/workspace
```

The workspace must contain a valid `manifest.tsv` and completed BFLOW products.

## 6. Dry-run and full execution

Inspect the plan without creating files or submitting jobs:

```bash
mpas-bmatrix build \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage plots \
  --dry-run
```

Run the complete workflow:

```bash
mpas-bmatrix build \
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
mpas-bmatrix build \
  --bflow-workspace "$BFLOW" \
  --from-stage vbal \
  --to-stage plots \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean \
  --poll-seconds 30
```

The installed `mpas-bmatrix` command is the public user interface. Explicit
`PYTHONPATH=src` and `python -m bmatrix` invocations belong to developer/debug
workflows.

## 7. Run and validate one stage

Use the same stage in `--from-stage` and `--to-stage`:

```bash
mpas-bmatrix build \
  --bflow-workspace "$BFLOW" \
  --from-stage hdiag \
  --to-stage hdiag \
  --clean \
  --poll-seconds 30
```

Validate a completed stage without rerunning it:

```bash
mpas-bmatrix validate \
  --bflow-workspace "$BFLOW" \
  --stage hdiag
```

Valid stage names are:

```text
bflow, vbal, unbalance, hdiag, nicas, so, dirac, plots
```

## 8. What each stage consumes and produces

The complete file matrix and acceptance criteria are in
[`stage-products.md`](stage-products.md). The operator summary is:

### BFLOW

**Input:** same-valid-time f048/f024 forecasts.

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

### UNBALANCE

**Input:** VBAL products and centered perturbations.

**Purpose:** apply K2^-1 and explicitly write the unbalanced ensemble used by
HDIAG.

**Main outputs:**

```text
samplesUnbalanced/PTB_f48mf24_*.nc
```

### HDIAG

**Input:** unbalanced samples.

**Purpose:** estimate standard deviations and horizontal/vertical correlation
scales.

**Main outputs:**

```text
HDIAG/mpas.stddev.nc
HDIAG/mpas.cor_rh.nc
HDIAG/mpas.cor_rv.nc
```

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

### DIRAC

**Input:** calibrated complete B.

**Purpose:** write the complete-B response to one configured impulse.

**Main output:**

```text
DIRAC/mpas.dirac.nc
```

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

## 9. Find reusable products and paths

For infrastructure/resource paths:

```bash
mpas-bmatrix paths
```

For reusable scientific products associated with an existing BFLOW workspace:

```bash
mpas-bmatrix products --bflow-workspace "$BFLOW"
```

This distinction is intentional:

```text
paths      -> software, mesh, static data and workspace roots
products   -> B-matrix scientific files generated by a run
```

## 10. Configuration changes and reruns

Start from the earliest affected stage and include `--clean`:

```text
controls or BFLOW changed
  -> rerun from BFLOW

VBAL changed
  -> rerun from VBAL

UNBALANCE changed
  -> rerun from UNBALANCE

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

## 11. Troubleshooting sequence

When a stage fails:

1. stop the pipeline at the failed stage;
2. run `mpas-bmatrix doctor` if the failure can be infrastructure-related;
3. run `mpas-bmatrix paths` and confirm the resolved resources;
4. inspect the generated YAML and PBS script in the failed stage workspace;
5. inspect `stdout.log`, `stderr.log` and the stage runlog;
6. run `mpas-bmatrix validate --stage <stage>`;
7. use `mpas-bmatrix check-config --json` for the complete resolved contract;
8. verify every required upstream product before retrying;
9. rerun only from the earliest invalid stage with `--clean`.

See [`operations.md`](operations.md) for known scientific/operational errors.

## 12. Reproducibility record

For each test or production run, record:

```text
MPAS-BMatrix commit
configuration entry point
configuration_sources
bmatrix_contract_sources
mpaswf manifest or BFLOW workspace
stage range
resolved path/resource report
PBS job IDs
main log path
final product paths
validation result
```

The end-to-end smoke template remains in [`end-to-end-tutorial.md`](end-to-end-tutorial.md).
