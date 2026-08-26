# End-to-end JACI smoke test

This procedure verifies the complete operational chain used to produce MPAS-JEDI
static B-matrix products:

```text
GFS/WPS/MPAS (mpaswf)
        ↓
forecast-pair manifest
        ↓
BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
        (MPAS-BMatrix)
```

The smoke test answers an operational question: **does the complete system still
work from upstream MPAS preparation through the final B-matrix diagnostics?**

It does not prove that the selected number of NMC samples is statistically
sufficient for a production-quality B-matrix.

## 1. Record the test identity

Before starting, record:

```text
tester:
date:
JACI login node:
mpaswf commit:
MPAS-BMatrix commit:
mpaswf configuration:
MPAS-BMatrix configuration:
campaign valid-time range:
```

At the end also record PBS job IDs, main log paths, the manifest path, final
product paths and validation result.

## 2. Install the two public workflows

Use separate source checkouts. The runtime products do not need to live inside
either repository.

```bash
git clone https://github.com/joaogerd/mpaswf.git
git clone https://github.com/joaogerd/MPAS-BMatrix.git

python -m pip install --no-deps -e ./mpaswf
python -m pip install -e ./MPAS-BMatrix

mpaswf --help
mpas-bmatrix --help
```

Record the exact revisions:

```bash
git -C mpaswf rev-parse HEAD
git -C MPAS-BMatrix rev-parse HEAD
```

## 3. Configure and validate MPAS-BMatrix first

MPAS-BMatrix should not require a new user to begin by exporting a list of opaque
paths. On JACI:

```bash
mpas-bmatrix setup --site jaci
mpas-bmatrix paths
mpas-bmatrix doctor
mpas-bmatrix check-config
```

`paths` explains every resolved resource and where it came from. `doctor`
validates the concrete software, mesh, static files and MPI partition.

Do not continue to the expensive part of the smoke if `doctor` does not end in:

```text
READY
```

For the reproducibility record, save the complete configuration:

```bash
mpas-bmatrix check-config --json > mpas-bmatrix-resolved-config.json
mpas-bmatrix paths --json > mpas-bmatrix-resolved-paths.json
```

## 4. Configure the upstream MPASWF campaign

MPASWF owns:

```text
GFS f000
  -> WPS/ungrib
  -> mesh static interpolation
  -> date-dependent MPAS initialization
  -> f024/f048 forecasts
  -> restart + da_state products
  -> neutral forecast-pair manifest
```

Use the validated MPASWF JACI configuration and campaign described in its own
`docs/getting-started.md`. The recommended current entry point is:

```bash
cd mpaswf
CONFIG=configs/jaci-x1.10242.yaml
```

The campaign dates in the MPASWF contract are **valid times**. For each valid
time `T`, the hand-off must contain:

```text
f048 initialized at T - 48 h and valid at T
f024 initialized at T - 24 h and valid at T
```

For a smoke test, use a small validated range. For a production B-matrix, use the
scientifically required sample population instead.

## 5. Verify PBS/MPI before running MPAS

Run the real MPASWF scheduler smoke:

```bash
mpaswf pbs-smoke --config "$CONFIG"
```

This must perform an actual `qsub`/`qstat` round trip and execute on a compute
node. Do not treat a login-node-only command test as equivalent.

Acceptance:

```text
PBS job submitted successfully
compute-node payload executed
pbs-smoke.ok produced
command exits with status 0
```

If this fails, fix the scheduler/MPI/runtime environment before continuing.

## 6. Run the complete upstream MPAS sequence

### 6.1 Prepare GFS/WPS inputs

```bash
mpaswf run --phase prepare --config "$CONFIG"
```

Expected behavior:

```text
locate/download each required GFS f000 analysis
stage WPS
render namelist.wps
run link_grib.csh + ungrib.exe
validate FILE:YYYY-MM-DD_HH products
```

### 6.2 Generate static and date-dependent MPAS initial states

```bash
mpaswf run --phase init --config "$CONFIG" --submit --wait
```

Expected behavior:

```text
generate or reuse the mesh static product
submit MPAS initialization jobs
wait for completion
validate every required initial state
```

### 6.3 Run f024/f048 forecasts

```bash
mpaswf run --phase forecast --config "$CONFIG" --submit --wait
```

Expected behavior:

```text
run all required 24 h and 48 h MPAS integrations
produce restart products
produce da_state products
validate each requested lead
```

### 6.4 Build the neutral hand-off manifest

```bash
mpaswf run --phase manifest --config "$CONFIG"
```

MPASWF writes:

```text
<mpaswf-work-dir>/products/mpas-forecast-manifest.tsv
```

The manifest contains same-valid-time f048/f024 pairs consumed by MPAS-BMatrix.
Record its absolute path:

```bash
MANIFEST=/absolute/path/to/products/mpas-forecast-manifest.tsv
test -s "$MANIFEST"
```

Do not move to BFLOW until MPASWF has validated the complete requested manifest.

## 7. Inspect the MPAS-BMatrix plan

Return to any directory; the installed public command should not require the
current directory to be the MPAS-BMatrix checkout.

```bash
mpas-bmatrix build \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage plots \
  --dry-run
```

Review at least:

```text
selected stages
BFLOW workspace
covariance workspaces
plots workspace
final reusable product paths
```

The standard workspace layout is:

```text
<WORK_ROOT>/bmatrix/
├── bflow_preprocessing/<RUN>/
├── covariance/
│   ├── vbal/<RUN>/
│   ├── unbalance/<RUN>/
│   ├── hdiag/<RUN>/
│   ├── nicas/<RUN>/
│   ├── so/<RUN>/
│   └── dirac/<RUN>/
└── plots/<RUN>/
```

## 8. Run the complete B-matrix chain

For a clean smoke run:

```bash
mpas-bmatrix build \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage plots \
  --clean \
  --poll-seconds 30
```

The pipeline is dependency ordered. A downstream stage is not considered ready
merely because a PBS job disappeared from the queue: each stage must pass its
product validation before the next stage is accepted.

## 9. Stage acceptance checks

Use [`stage-products.md`](stage-products.md) for the complete file contract. The
minimum end-to-end smoke acceptance is:

### BFLOW

Inputs:

```text
same-valid-time f048/f024 MPAS states from the manifest
```

Required products include:

```text
FULL_f48.nc
FULL_f24.nc
PTB_f48mf24.nc
template_PTB.nc
manifest.tsv
ESMF_weights/weights_manifest.json
```

### VBAL

Required products include:

```text
mpas_vbal.nc
mpas_sampling.nc
local VBAL/sampling products for the configured MPI layout
```

### UNBALANCE

Required product population:

```text
samplesUnbalanced/PTB_f48mf24_*.nc
```

The member count must match the accepted input sample population.

### HDIAG

Required products:

```text
mpas.stddev.nc
mpas.cor_rh.nc
mpas.cor_rv.nc
```

The fields must be readable, dimensionally consistent and nontrivial.

### NICAS

Required merged products include:

```text
mpas_nicas.nc
mpas.nicas_norm.nc
mpas.dirac_nicas.nc
merge.done
```

### SO

Acceptance requires a successful OOPS variational single-observation run and its
expected analysis/observation outputs. A visually small or zero difference in an
individual MPAS-native field is not by itself proof of failure; use the stage
validator and runlog contract.

### DIRAC

Required product:

```text
mpas.dirac.nc
```

It must be readable and contain a nontrivial complete-B response to the configured
impulse.

### PLOTS

Required diagnostics include:

```text
summary.csv
README.md
scientific figure directories
```

Plots must be physically interpretable; successful PNG creation alone is not a
scientific acceptance criterion.

## 10. Validate stages independently after the run

Keep the BFLOW workspace reported by the dry-run/build:

```bash
BFLOW=/absolute/path/to/bflow/workspace
```

Then:

```bash
for stage in bflow vbal unbalance hdiag nicas so dirac plots; do
  mpas-bmatrix validate \
    --bflow-workspace "$BFLOW" \
    --stage "$stage" || break
done
```

List the reusable final scientific products:

```bash
mpas-bmatrix products --bflow-workspace "$BFLOW"
```

## 11. What counts as a successful system smoke

The smoke is successful only when **all** of the following are true:

- MPASWF real PBS smoke succeeds on a compute node;
- GFS/WPS preparation succeeds for every required cycle;
- MPAS static/init phases succeed;
- every requested f024/f048 forecast succeeds;
- MPASWF validates and writes the complete forecast-pair manifest;
- MPAS-BMatrix `doctor` reports `READY`;
- BFLOW succeeds for every manifest pair;
- VBAL succeeds and validates;
- UNBALANCE succeeds and validates the member population;
- HDIAG succeeds and validates;
- NICAS jobs and merge succeed and validate;
- SO succeeds and validates;
- DIRAC succeeds and validates;
- PLOTS succeeds and validates;
- `mpas-bmatrix products` resolves the expected reusable B-matrix products.

This complete-system check is important after changes to the environment,
MONAN-JEDI/MPAS-JEDI installation, mesh/static resources, workflow contracts or
stage interfaces. Unit tests alone do not replace it.

## 12. Failure handling

When a stage fails:

1. stop at the failed stage;
2. record the PBS job ID and workspace;
3. inspect generated YAML/PBS scripts and stdout/stderr/runlogs;
4. run `mpas-bmatrix doctor` for infrastructure-related failures;
5. run `mpas-bmatrix paths` to verify exactly which resources were selected;
6. run `mpas-bmatrix validate --stage <stage>` for an already-created workspace;
7. fix the root cause;
8. rerun from the earliest invalid stage with `--clean` when regeneration is required.

Do not hide a failed upstream stage by reusing downstream products from an older
configuration.

## 13. Final test record

Record at least:

```text
mpaswf commit
MPAS-BMatrix commit
MPASWF resolved configuration/campaign
MPAS-BMatrix resolved configuration
MPAS-BMatrix resolved path report
manifest path
BFLOW workspace
stage workspaces
PBS job IDs
main logs
final product paths
per-stage validation result
end-to-end PASS/FAIL
```

A reproducible smoke report should let another colleague identify which software,
inputs and runtime resources produced the result without guessing from shell
history.
