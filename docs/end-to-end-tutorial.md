# End-to-end smoke tutorial

This tutorial is intended for a colleague who needs to test the complete
`MPAS-BMatrix` workflow for the first time.

The smoke test verifies that the complete operational chain works:

```text
mpaswf -> BFLOW -> VBAL -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

It does **not** prove that the number of NMC samples is sufficient for a
production-quality B-matrix. It proves that the repositories, environment,
configuration, executables, scheduler jobs and product interfaces are working.

## 1. Information the tester must report

Before starting, create a text file or laboratory note containing:

```text
tester name:
machine/login node:
MPAS-BMatrix commit:
mpaswf commit:
configuration entry point:
mpaswf manifest or existing BFLOW workspace:
start date/time:
```

At the end, add job IDs, log paths, validation results and missing products.

## 2. Create the Python environment and install both tools

Before cloning or running the scientific workflow, follow
[Installation on JACI](install-jaci.md). That guide:

- creates the `monan-jedi-bmatrix` Conda environment with Python 3.11;
- installs MPASWF and MPAS-BMatrix;
- loads the scientific JACI environment without mixing two Python installations;
- verifies the origins of Python and NumPy.

Do not continue until these commands succeed:

```bash
conda activate monan-jedi-bmatrix
mpaswf --help
mpas-bmatrix --help
python -c "import sys, numpy; print(sys.executable); print(numpy.__file__)"
```

Both printed paths must belong to the active Conda environment.

## 3. Use the repositories installed by the guide

The installation guide defines:

```bash
export PROJECT_ROOT="/p/projetos/monan_das/$USER/projects"
export WORK_ROOT="/p/projetos/monan_das/$USER/work/MPAS-BMatrix"
export BMATRIX_ROOT="$PROJECT_ROOT/MPAS-BMatrix"
export MPASWF_ROOT="$PROJECT_ROOT/mpaswf"
```

Record the tested revisions:

```bash
git -C "$BMATRIX_ROOT" rev-parse HEAD
git -C "$MPASWF_ROOT" rev-parse HEAD
```

Use `main` unless a specific test branch was requested. For this migration use
`feature/in-memory-vbal-hdiag` until it is merged.

## 4. Declare the JACI x1.10242 paths

```bash
export MONAN_JEDI_INSTALL_ROOT="/p/projetos/monan_das/$USER/build/monan-jedi"
export STACK_ROOT="/p/projetos/monan_das/joao.gerd/work/spack-stack-inpe-overlay-20260515T181917Z/spack-stack"
```

The mesh, its 128-part partition and the static x1.10242 files already have
concrete JACI paths in `configs/jaci-x1.10242.yaml`. The expression `$USER`
is replaced automatically by the current login name. Users should verify that
those shared inputs exist; they do not need to invent or export alternative
mesh paths.

The production workflow requires `mpasjedi_error_covariance_toolbox.x` and
`mpasjedi_variational.x`. It does not require
`mpasjedi_unbalance_ensemble.x`; that executable is used only by the retained
legacy A/B reference path.

## 5. Load the JACI scientific environment

The Python environment and both tools were installed in Section 2. Load the
scientific programs and libraries required by MPAS-JEDI:

```bash
conda activate monan-jedi-bmatrix
cd "$BMATRIX_ROOT"
source scripts/load_jaci_env.sh
```

The script preserves the Conda Python and removes Python search paths inserted by
spack-stack. Verify before continuing:

```bash
command -v python
command -v mpaswf
command -v mpas-bmatrix
python -c "import sys, numpy; print(sys.version); print(sys.executable); print(numpy.__file__)"
```

The Python executable, `mpaswf`, `mpas-bmatrix` and NumPy must come from the
same Conda environment.

## 6. Validate the composed configuration

```bash
cd "$BMATRIX_ROOT"
export CONFIG=configs/jaci-x1.10242.yaml
mpas-bmatrix check-config \
  --config "$CONFIG" > "$WORK_ROOT/check-config.json"
less "$WORK_ROOT/check-config.json"
```

Minimum acceptance:

- command exits with status 0;
- no unresolved environment variables remain;
- paths, mesh and MPI size are correct;
- MPAS-JEDI runtime/static files resolve correctly;
- production sections `controls`, `bflow`, `vbal`, `hdiag`, `nicas`,
  `single_observation` and `dirac` are present;
- the optional `unbalance` section may remain loaded for migration A/B testing,
  but it is not a production stage;
- configuration provenance is recorded.

## 7. Locate the file containing the forecast pairs

MPASWF writes a tab-separated text file listing each valid time and the
corresponding 48 h and 24 h forecasts. The technical name of this file is
`mpas-forecast-manifest.tsv`.

With the standard JACI configuration, its location is:

```bash
export MANIFEST="/p/projetos/monan_das/$USER/work/mpaswf/products/mpas-forecast-manifest.tsv"
```

The expression `$USER` is replaced automatically by the current JACI login
name. For example, for `liviany.viana`, the path becomes:

```text
/p/projetos/monan_das/liviany.viana/work/mpaswf/products/mpas-forecast-manifest.tsv
```

This file is not created manually. It is generated after the MPAS forecasts by:

```bash
cd "$MPASWF_ROOT"
mpaswf run --phase manifest --config configs/jaci-x1.10242.yaml
```

Confirm that the file exists and inspect its first lines:

```bash
test -s "$MANIFEST" || {
  echo "Forecast-pair file not found: $MANIFEST"
  return 1 2>/dev/null || exit 1
}
head "$MANIFEST"
mpas-bmatrix check-manifest --manifest "$MANIFEST"
```

Alternatively, a test may resume from an existing BFLOW directory. In that case:

```bash
export BFLOW="$WORK_ROOT/bmatrix/bflow_preprocessing/np128_<START_VALID>_<END_VALID>"
test -s "$BFLOW/manifest.tsv"
find "$BFLOW/output" -name 'PTB_f48mf24.nc' | sort
```

## 8. Inspect the execution plan

```bash
mpas-bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage plots \
  --dry-run | tee "$WORK_ROOT/pipeline-plan.json"
```

The plan must contain:

```text
bflow -> vbal -> hdiag -> nicas -> so -> dirac -> plots
```

and must not contain `unbalance`.

## 9. Run and validate BFLOW

```bash
mpas-bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage bflow \
  --clean --poll-seconds 30
```

Then validate BFLOW and export its deterministic workspace.

## 10. Run VBAL through PLOTS

```bash
mpas-bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage vbal \
  --to-stage plots \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean \
  --poll-seconds 30 \
  2>&1 | tee "$WORK_ROOT/bmatrix-end-to-end.log"
```

The orchestrator waits for and validates each dependency. During HDIAG, confirm
that the generated YAML reads `../samples/PTB_f48mf24_%mem%.nc` and includes
`BUMP_VerticalBalance` as a SABER outer block reading the VBAL/sampling products.
No `samplesUnbalanced` output is expected.

## 11. Validate every production stage

```bash
for stage in bflow vbal hdiag nicas so dirac plots; do
  mpas-bmatrix validate \
    --config "$CONFIG" \
    --bflow-workspace "$BFLOW" \
    --stage "$stage" || break
done
```

## 12. Minimum artifact checklist

```text
BFLOW
  manifest.tsv
  output/*/FULL_f24.nc
  output/*/FULL_f48.nc
  output/*/PTB_f48mf24.nc

VBAL
  mpas_vbal.nc
  mpas_sampling.nc
  local VBAL/sampling products
  samples/PTB_f48mf24_*.nc

HDIAG
  mpas.stddev.nc
  mpas.cor_rh.nc
  mpas.cor_rv.nc

NICAS
  merge/mpas_nicas.nc
  local/grid products
  merge/mpas.nicas_norm.nc
  merge/mpas.dirac_nicas.nc
  merge/merge.done

SO
  an.*.nc
  obsout_SO_T.h5
  obsout_SO_U.h5
  run_SO.runlog

DIRAC
  mpas.dirac.nc

PLOTS
  summary.csv
  README.md
  diagnostic figure directories
```

There is intentionally no production `UNBALANCE` artifact set.

## 13. Migration A/B validation

Before removing the retained legacy path, follow
[`in-memory-vbal-hdiag.md`](in-memory-vbal-hdiag.md). Use the same BFLOW/VBAL
inputs to compare the old materialized and new in-memory paths through HDIAG,
NICAS, DIRAC and SO.

## 14. Development checks

```bash
cd "$BMATRIX_ROOT"
mkdir -p .pytest-tmp
TMPDIR="$BMATRIX_ROOT/.pytest-tmp" \
python -m pytest -p no:cacheprovider -q
python -m ruff check src/bmatrix tests
git diff --check
```

## 15. Failure report template

```text
Tester:
Machine/login node:
MPAS-BMatrix commit:
mpaswf commit:
CONFIG:
configuration_sources:
bmatrix_contract_sources:
MANIFEST or BFLOW:
Command executed:
First failed stage:
PBS job ID:
Exit status:
Main log:
Stage runlog:
Last 50 relevant log lines:
Expected artifact missing or invalid:
Resolved path/value suspected:
Development test result:
Additional observations:
```

The most useful report identifies the first invalid stage and includes the exact
resolved configuration plus log/product paths.
