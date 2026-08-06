# End-to-end smoke tutorial

This tutorial is the document to send to a colleague who needs to test the full
`MPAS-BMatrix` workflow for the first time.

The goal is not to produce a statistically robust production B-matrix. The goal
is to verify that the complete sequence is operational, reproducible and produces
all expected artifacts:

```text
mpaswf -> BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

`mpaswf` is the upstream workflow that generates MPAS forecast pairs. From
`BFLOW` onward, the workflow is owned by this repository.

## 0. What this test proves

A successful end-to-end smoke run proves that:

- the repositories can be cloned and installed;
- the MPAS-JEDI runtime environment can be loaded;
- the configuration resolves correctly;
- MPAS f024/f048 forecast pairs or a compatible manifest are available;
- BFLOW can prepare the training perturbations;
- VBAL, UNBALANCE, HDIAG and NICAS can build the static B products;
- SO can use those products inside `mpasjedi_variational.x`;
- DIRAC can produce the complete-B impulse response;
- PLOTS can generate diagnostic figures and summaries.

It does not prove that the sample size is scientifically sufficient for
production. For production, increase the number of NMC samples and repeat the
same acceptance checks.

## 1. Choose generic roots

Ask the tester to choose a project area and a work area. These examples are
placeholders and must be adapted to the target machine/account:

```bash
export PROJECT_ROOT=/path/to/projects
export WORK_ROOT=/path/to/work/MPAS-BMatrix
export STACK_ROOT=/path/to/spack-stack

mkdir -p "$PROJECT_ROOT" "$WORK_ROOT"
```

On JACI, use a persistent project filesystem for `WORK_ROOT`; do not use `/tmp`
for this workflow.

## 2. Clone the repositories

```bash
cd "$PROJECT_ROOT"

git clone https://github.com/joaogerd/MPAS-BMatrix.git
git clone https://github.com/joaogerd/mpaswf.git

export BMATRIX_ROOT="$PROJECT_ROOT/MPAS-BMatrix"
export MPASWF_ROOT="$PROJECT_ROOT/mpaswf"
```

If the test must use an open documentation branch, check it out explicitly:

```bash
cd "$BMATRIX_ROOT"
git fetch origin
git checkout docs/main-documentation
```

After the documentation PR is merged, use `main` instead.

## 3. Load the environment and install packages

The B-matrix repository contains a path-generic JACI loader. Set `STACK_ROOT`
first, then source the loader:

```bash
cd "$BMATRIX_ROOT"
source scripts/load_jaci_env.sh
```

Install both Python packages in the active environment:

```bash
python -m pip install --no-deps -e "$MPASWF_ROOT"
python -m pip install -e "$BMATRIX_ROOT"
```

For optional diagnostics and development checks:

```bash
python -m pip install -e "$BMATRIX_ROOT[diagnostics,dev]"
```

Minimum acceptance:

```bash
command -v mpaswf
command -v mpas-bmatrix || true
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix --help
```

The installed console command and the module invocation should both be usable. If
only the module invocation works, continue the smoke test with:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix <subcommand>
```

## 4. Prepare the configuration

The default B-matrix configuration used by this repository is:

```bash
cd "$BMATRIX_ROOT"
export CONFIG=configs/jaci-x1.10242.yaml
```

Before running anything expensive, inspect and validate the resolved
configuration:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix check-config \
  --config "$CONFIG"
```

Minimum acceptance:

- the command exits successfully;
- mesh, static paths, executable paths and PBS settings resolve to the intended
  machine-specific locations;
- `configs/bmatrix-x1.10242.yaml` is included as the scientific contract.

If this fails, fix paths and environment first. Do not continue to pair
generation or B-matrix stages.

## 5. Generate forecast pairs with mpaswf

Use this path when the tester needs to generate pairs from scratch.

Create or select an `mpaswf` configuration file. The exact configuration is
machine-specific and must define the MPAS mesh/static files, date range, forecast
lead times, WPS/GFS settings and work directory.

```bash
cd "$MPASWF_ROOT"
export MPASWF_CONFIG=/path/to/mpaswf-config.yaml
```

Run the upstream workflow:

```bash
mpaswf run --phase prepare  --config "$MPASWF_CONFIG"
mpaswf run --phase init     --config "$MPASWF_CONFIG" --submit --wait
mpaswf run --phase forecast --config "$MPASWF_CONFIG" --submit --wait
mpaswf run --phase manifest --config "$MPASWF_CONFIG"
```

The NMC pair for each valid time `T` is:

```text
f048 initialized at T - 48 h
minus
f024 initialized at T - 24 h
```

Set the manifest path produced by `mpaswf`:

```bash
export MANIFEST=/path/to/mpaswf-work/products/mpas-forecast-manifest.tsv
```

Minimum acceptance:

```bash
test -s "$MANIFEST"
head -n 5 "$MANIFEST"
```

The manifest must point to readable f024/f048 products for each valid time.

## 6. Alternative: start from an existing BFLOW workspace

Use this path when forecast pairs and BFLOW products were already prepared.

```bash
export BFLOW="$WORK_ROOT/bmatrix/bflow_preprocessing/np128_<START_VALID>_<END_VALID>"
```

Minimum acceptance:

```bash
test -s "$BFLOW/manifest.tsv"
find "$BFLOW/output" -name 'PTB_f48mf24.nc' | sort
find "$BFLOW/output" -name 'FULL_f24.nc' | sort
find "$BFLOW/output" -name 'FULL_f48.nc' | sort
```

If this passes, skip directly to Section 8.

## 7. Run BFLOW from the mpaswf manifest

Return to the B-matrix repository:

```bash
cd "$BMATRIX_ROOT"
```

Run only BFLOW first. This makes the hand-off from `mpaswf` explicit and easier
to debug:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage bflow \
  --clean \
  --poll-seconds 30
```

Then identify the BFLOW workspace produced by the run. If the configuration uses
the standard layout, it follows this pattern:

```bash
export BFLOW="$WORK_ROOT/bmatrix/bflow_preprocessing/np128_<START_VALID>_<END_VALID>"
```

Minimum acceptance:

```bash
test -s "$BFLOW/manifest.tsv"
find "$BFLOW/output" -name 'PTB_f48mf24.nc' | sort
find "$BFLOW/output" -name 'FULL_f24.nc' | sort
find "$BFLOW/output" -name 'FULL_f48.nc' | sort
```

Do not continue until BFLOW products exist for the expected number of members.

## 8. Run the complete workflow through plots

For a first tester run, execute the full pipeline through `PLOTS` from the BFLOW
workspace:

```bash
cd "$BMATRIX_ROOT"

PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --to-stage plots \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean \
  --poll-seconds 30 \
  2>&1 | tee "$WORK_ROOT/end_to_end_smoke.log"
```

This command runs:

```text
VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

Minimum acceptance:

```bash
test -s "$WORK_ROOT/end_to_end_smoke.log"
grep -Ei 'error|failed|traceback|segmentation|signal' "$WORK_ROOT/end_to_end_smoke.log" || true
```

A non-empty grep result is not always fatal, but every match must be inspected.

## 9. Validate individual stages

Run the public validator after the build completes:

```bash
for stage in bflow vbal unbalance hdiag nicas so dirac plots; do
  PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix validate \
    --config "$CONFIG" \
    --bflow-workspace "$BFLOW" \
    --stage "$stage"
done
```

Also inspect the product contract:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix products \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW"
```

## 10. Check required artifacts manually

Use these checks as a quick checklist before reporting success.

### VBAL

```bash
find "$WORK_ROOT" -path '*VBAL/mpas_vbal.nc' -o -path '*VBAL/mpas_sampling.nc'
find "$WORK_ROOT" -path '*VBAL/mpas_vbal_local_*' | head
find "$WORK_ROOT" -path '*VBAL/mpas_sampling_local_*' | head
```

### UNBALANCE

```bash
find "$WORK_ROOT" -path '*samplesUnbalanced/PTB_f48mf24_*.nc' | sort
```

### HDIAG

```bash
find "$WORK_ROOT" -path '*HDIAG/mpas.stddev.nc'
find "$WORK_ROOT" -path '*HDIAG/mpas.cor_rh.nc'
find "$WORK_ROOT" -path '*HDIAG/mpas.cor_rv.nc'
```

### NICAS

```bash
find "$WORK_ROOT" -path '*NICAS/merge/mpas_nicas.nc'
find "$WORK_ROOT" -path '*NICAS/merge/mpas.nicas_norm.nc'
find "$WORK_ROOT" -path '*NICAS/merge/mpas.dirac_nicas.nc'
find "$WORK_ROOT" -path '*NICAS/merge/merge.done'
```

### SO

```bash
find "$WORK_ROOT" -path '*SO/run_SO.runlog'
find "$WORK_ROOT" -path '*SO/obsout_SO_*.h5'
find "$WORK_ROOT" -path '*SO/an.*.nc'
```

The SO runlog should show a successful variational run and include:

```text
CostFunction::addIncrement: Analysis
```

### DIRAC

```bash
find "$WORK_ROOT" -path '*DIRAC/mpas.dirac.nc'
find "$WORK_ROOT" -path '*DIRAC/run_dirac.runlog'
```

### PLOTS

```bash
find "$WORK_ROOT" -path '*plots*/summary.csv'
find "$WORK_ROOT" -path '*plots*' -type f \( -name '*.png' -o -name '*.pdf' \) | head
```

## 11. Acceptance report for the tester

Ask the tester to send back this information:

```text
Repository commit:
MPAS-BMatrix branch:
mpaswf commit:
Machine/cluster:
CONFIG used:
MPASWF_CONFIG used, if pairs were generated:
MANIFEST path, if used:
BFLOW workspace:
WORK_ROOT:
Command used:
End-to-end log path:
Stages validated:
Missing artifacts, if any:
Errors or warnings inspected:
```

A successful smoke report should state that all stages validated and that the
required artifacts listed in Section 10 exist.

## 12. Common failure points

### Configuration does not resolve

Run:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix check-config --config "$CONFIG"
```

Fix paths to executables, mesh files, static files, PBS queues or `STACK_ROOT`.
Do not continue until the configuration resolves cleanly.

### BFLOW products are missing

Check whether the `mpaswf` manifest points to readable f024/f048 products. If
not, fix the upstream `mpaswf` run first.

### UNBALANCE products are missing

Do not run HDIAG directly from raw PTBs. The current official stage order expects
`UNBALANCE` to create `samplesUnbalanced/PTB_f48mf24_*.nc` before HDIAG.

### HDIAG fails with a BUMP radius or universe error

Check the HDIAG distance class count and distance class width in the scientific
configuration.

### NICAS fails with `wrong size for dimension nl0`

Check that 2D `surface_pressure` reads are separated from the 3D control group in
`BUMP_NICAS.read.grids`.

### SO finishes but `an-bg` looks zero in MPAS-native fields

This is not automatically a failure. `SO/an.*.nc` is written through MPAS-native
streams and does not necessarily expose canonical JEDI increments directly. Use
runlog success, obsout files and the public validator as the first acceptance
criteria.

## 13. Next documents

After completing this tutorial, use:

```text
docs/stage-products.md       detailed acceptance matrix
docs/user-guide.md           operational guide
docs/mpaswf-pairs.md         upstream pair generation details
docs/operations.md           troubleshooting
docs/bmatrix-theory.md       scientific background
docs/developer-guide.md      implementation and extension rules
```
