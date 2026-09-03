# Stage products and acceptance criteria

This document is the user-facing acceptance matrix for the sequential
`MPAS-BMatrix` workflow. Use it to decide whether a stage produced valid outputs
before running the next stage.

The full production order is:

```text
mpaswf -> BFLOW -> VBAL -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

`mpaswf` is external. All stages from BFLOW onward belong to this repository.

## Acceptance matrix

| Stage | Main inputs | Main outputs | Acceptance criteria |
| --- | --- | --- | --- |
| `mpaswf` | GFS/WPS inputs, MPAS mesh/static files, mpaswf config | `mpas-forecast-manifest.tsv` | Manifest exists; f048 and f024 files exist for each valid time; paths are readable. |
| `bflow` | `mpaswf` manifest or existing forecast pairs | `FULL_f24.nc`, `FULL_f48.nc`, `PTB_f48mf24.nc`, `manifest.tsv`, `ESMF_weights/weights_manifest.json` | Member directories exist; products exist for each member; expected variables are present; weights manifest exists when regridding is used. |
| `vbal` | BFLOW samples and static files | `mpas_vbal.nc`, `mpas_sampling.nc`, `mpas_vbal_local_*`, `mpas_sampling_local_*` | PBS job exits successfully; global and local products exist; runlog reports successful completion. |
| `hdiag` | Original VBAL-staged NMC perturbations plus VBAL/sampling products | `mpas.stddev.nc`, `mpas.cor_rh.nc`, `mpas.cor_rv.nc` | HDIAG reads `samples/PTB_f48mf24_*.nc`, applies inverse VBAL in memory, products exist, dimensions match mesh/control variables, fields are not entirely missing or trivially zero, and no BUMP radius error appears in logs. |
| `nicas` | HDIAG correlation scales and stddev | `merge/mpas_nicas.nc`, local NICAS products, grids, `mpas.nicas_norm.nc`, `mpas.dirac_nicas.nc`, `merge.done` | All per-variable jobs and merge complete; merged global/local/grid products exist; 2D surface pressure remains separated from 3D controls for reads. |
| `so` | NICAS merge, HDIAG stddev, VBAL products | `obsout_SO_T.h5`, `obsout_SO_U.h5`, `an.*.nc`, `run_SO.runlog` | OOPS status is successful; `CostFunction::addIncrement: Analysis` appears in log; obsout and analysis files exist. |
| `dirac` | NICAS merge, HDIAG stddev, VBAL products | `mpas.dirac.nc` | Run completes successfully; output exists and is readable; response is not entirely missing/trivial. |
| `plots` | Completed NetCDF products | `summary.csv`, plot directories and figures | Summary exists; expected directories exist; figures are generated for available products. |

## Stage details

### mpaswf

`mpaswf` produces the upstream same-valid-time forecast pairs. It is not a
B-matrix stage, but it is often the first operational step.

Expected manifest:

```text
<mpaswf work_dir>/products/mpas-forecast-manifest.tsv
```

Expected columns:

```text
valid_time    f048_state    f024_state    f048_restart    f024_restart
```

Minimum checks:

```bash
test -s "$MANIFEST"
head -n 5 "$MANIFEST"
```

### BFLOW

BFLOW turns MPAS forecast-pair products into covariance-training files.

Expected product pattern:

```text
$BFLOW/manifest.tsv
$BFLOW/output/<VALID_TIME>/FULL_f24.nc
$BFLOW/output/<VALID_TIME>/FULL_f48.nc
$BFLOW/output/<VALID_TIME>/PTB_f48mf24.nc
$BFLOW/template_PTB.nc
$BFLOW/ESMF_weights/weights_manifest.json
```

Minimum checks:

```bash
test -s "$BFLOW/manifest.tsv"
find "$BFLOW/output" -name 'PTB_f48mf24.nc' | sort
find "$BFLOW/output" -name 'FULL_f24.nc' | sort
find "$BFLOW/output" -name 'FULL_f48.nc' | sort
```

### VBAL

VBAL calibrates the vertical/multivariate balance products and stages the
original perturbation members that will be reused by HDIAG.

Expected product pattern:

```text
$VBAL/VBAL/mpas_vbal.nc
$VBAL/VBAL/mpas_sampling.nc
$VBAL/VBAL/mpas_vbal_local_*
$VBAL/VBAL/mpas_sampling_local_*
$VBAL/samples/PTB_f48mf24_*.nc
```

Minimum checks:

```bash
test -s "$VBAL/VBAL/mpas_vbal.nc"
test -s "$VBAL/VBAL/mpas_sampling.nc"
ls "$VBAL/VBAL"/mpas_vbal_local_* | wc -l
ls "$VBAL/VBAL"/mpas_sampling_local_* | wc -l
find "$VBAL/samples" -name 'PTB_f48mf24_*.nc' | sort
```

Important note: `mpas_vbal.nc` may use NetCDF groups. Tools that inspect only the
root group can make the file look empty even when it is valid.

VBAL does not need to write `samplesUnbalanced` and does not rely on
`background error.output ensemble`.

### HDIAG

HDIAG computes the statistical diagnostics that feed NICAS and the final B.
It reads the original centered NMC perturbations from the VBAL workspace and
applies `BUMP_VerticalBalance` as a SABER outer block before BUMP_NICAS
calibration. The inverse balance transform therefore happens in memory.

Expected input pattern:

```text
$HDIAG/samples/PTB_f48mf24_*.nc
$HDIAG/vbal/mpas_vbal.nc
$HDIAG/vbal/mpas_sampling.nc
```

Expected product pattern:

```text
$HDIAG/HDIAG/mpas.stddev.nc
$HDIAG/HDIAG/mpas.cor_rh.nc
$HDIAG/HDIAG/mpas.cor_rv.nc
```

Minimum checks:

```bash
test -s "$HDIAG/HDIAG/mpas.stddev.nc"
test -s "$HDIAG/HDIAG/mpas.cor_rh.nc"
test -s "$HDIAG/HDIAG/mpas.cor_rv.nc"
ncdump -h "$HDIAG/HDIAG/mpas.stddev.nc" | head
grep -E 'BUMP_VerticalBalance|read vertical balance|Run: Finishing|status = 0' "$HDIAG/HDIAG/run_hdiag.runlog"
```

Troubleshooting cue: if the run fails with a BUMP universe/radius error, check
the HDIAG distance class count and width.

The historical `unbalance_core` remains available only for controlled A/B
validation; it is not a production stage. See
[`in-memory-vbal-hdiag.md`](in-memory-vbal-hdiag.md).

### NICAS

NICAS produces the spatial correlation/localization products and merges local
products for later reads.

Expected product pattern:

```text
$NICAS/merge/mpas_nicas.nc
$NICAS/merge/mpas_nicas_local_*
$NICAS/merge/mpas_nicas_grids_local_*
$NICAS/merge/mpas.nicas_norm.nc
$NICAS/merge/mpas.dirac_nicas.nc
$NICAS/merge/merge.done
```

Minimum checks:

```bash
test -s "$NICAS/merge/mpas_nicas.nc"
test -e "$NICAS/merge/merge.done"
ls "$NICAS/merge"/mpas_nicas_local_* | wc -l
ls "$NICAS/merge"/mpas_nicas_grids_local_* | wc -l
```

Troubleshooting cue: `wrong size for dimension nl0` usually means a 2D control
such as `surface_pressure` was read using the 3D NICAS grid.

### SO

SO validates the B inside a variational single-observation test.

Expected product pattern:

```text
$SO/run_SO.runlog
$SO/obsout_SO_T.h5
$SO/obsout_SO_U.h5
$SO/an.*.nc
```

Minimum checks:

```bash
grep -E 'CostFunction::addIncrement: Analysis|with status = 0' "$SO/run_SO.runlog"
ls "$SO"/obsout_SO_*.h5
ls "$SO"/an.*.nc
```

Important note: `an.*.nc` is MPAS-native output. It is not expected to contain
all canonical JEDI variable names.

### DIRAC

DIRAC validates the complete-B impulse response.

Expected product pattern:

```text
$DIRAC/mpas.dirac.nc
$DIRAC/run_dirac.runlog
```

Minimum checks:

```bash
test -s "$DIRAC/mpas.dirac.nc"
ncdump -h "$DIRAC/mpas.dirac.nc" | head
grep -E 'Run: Finishing|status = 0|Finished' "$DIRAC/run_dirac.runlog"
```

### PLOTS

PLOTS generates local diagnostic figures.

Expected product pattern:

```text
$PLOTS/summary.csv
$PLOTS/README.md
$PLOTS/01_stddev/
$PLOTS/02_corr_horizontal/
$PLOTS/03_corr_vertical/
$PLOTS/04_vbal/
$PLOTS/05_dirac/
$PLOTS/06_spatial_fields/
```

Minimum checks:

```bash
test -s "$PLOTS/summary.csv"
find "$PLOTS" -maxdepth 2 -type f \( -name '*.png' -o -name '*.pdf' \) | sort | head
```

## General validation commands

The public validator should be the first check when a stage exists:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix validate \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --stage <stage>
```

Use `products` to inspect the product contract:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix products \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW"
```
