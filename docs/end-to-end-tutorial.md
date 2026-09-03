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

## 2. Choose project and work roots

Use persistent storage. Do not use `/tmp` for generated workspaces or audit logs.

```bash
export PROJECT_ROOT=/path/to/projects
export WORK_ROOT=/path/to/work/MPAS-BMatrix
mkdir -p "$PROJECT_ROOT" "$WORK_ROOT"
```

## 3. Clone the repositories

```bash
cd "$PROJECT_ROOT"
git clone https://github.com/joaogerd/MPAS-BMatrix.git
git clone https://github.com/joaogerd/mpaswf.git
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
export MONAN_JEDI_INSTALL_ROOT=/p/projetos/monan_das/$USER/build/monan-jedi
export MPAS_MESH_ROOT=/path/to/mpas_meshes
export MPAS_JEDI_STATIC_ROOT=/path/to/validated/x1.10242/static-files
export STACK_ROOT=/path/to/spack-stack
```

The production workflow requires `mpasjedi_error_covariance_toolbox.x` and
`mpasjedi_variational.x`. It does not require
`mpasjedi_unbalance_ensemble.x`; that executable is used only by the retained
legacy A/B reference path.

## 5. Load the runtime and install packages

```bash
cd "$BMATRIX_ROOT"
source scripts/load_jaci_env.sh
python -m pip install --no-deps -e "$MPASWF_ROOT"
python -m pip install -e "$BMATRIX_ROOT"
```

For plotting and developer checks:

```bash
python -m pip install -e "$BMATRIX_ROOT[diagnostics,dev]"
```

## 6. Validate the composed configuration

```bash
cd "$BMATRIX_ROOT"
export CONFIG=configs/jaci-x1.10242.yaml
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix check-config \
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

## 7. Obtain the forecast-pair input

Generate f048/f024 forecasts and the manifest with `mpaswf`, or use an existing
BFLOW workspace.

For an existing BFLOW workspace:

```bash
export BFLOW="$WORK_ROOT/bmatrix/bflow_preprocessing/np128_<START_VALID>_<END_VALID>"
test -s "$BFLOW/manifest.tsv"
find "$BFLOW/output" -name 'PTB_f48mf24.nc' | sort
```

## 8. Inspect the execution plan

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
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
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage bflow \
  --clean --poll-seconds 30
```

Then validate BFLOW and export its deterministic workspace.

## 10. Run VBAL through PLOTS

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
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
  PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix validate \
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
PYTHONPATH="src:${PYTHONPATH:-}" \
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
