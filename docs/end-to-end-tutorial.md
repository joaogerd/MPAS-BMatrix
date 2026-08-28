# End-to-end smoke tutorial

This tutorial is intended for a colleague who needs to test the complete
`MPAS-BMatrix` workflow for the first time.

The smoke test verifies that the complete operational chain works:

```text
mpaswf -> BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
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

Use the `main` branch unless a specific test branch was explicitly requested.

## 4. Declare the JACI x1.10242 paths

The committed YAML files use one canonical MONAN-JEDI runtime prefix plus
separate mesh/case data paths:

```bash
export MONAN_JEDI_INSTALL_ROOT=/p/projetos/monan_das/$USER/build/monan-jedi

export MPAS_MESH_ROOT=/path/to/mpas_meshes
export MPAS_JEDI_STATIC_ROOT=/path/to/validated/x1.10242/static-files

export STACK_ROOT=/path/to/spack-stack
```

The B-matrix workflow derives JEDI/SABER executables from
`${MONAN_JEDI_INSTALL_ROOT}/bin`, MPAS runtime tables from
`${MONAN_JEDI_INSTALL_ROOT}/share/MPAS/core_atmosphere`, and MPAS-JEDI runtime
YAMLs from `${MONAN_JEDI_INSTALL_ROOT}/share/monan-jedi/mpas-jedi/namelists`.
The MONAN-JEDI source checkout and a separately configured unbalance executable
are not required. `MONAN_JEDI_INSTALL` remains accepted only as a legacy alias
when `MONAN_JEDI_INSTALL_ROOT` is not set.

The configured static directory must contain compatible files such as:

```text
x1.10242.invariant.nc
namelist.atmosphere_240km
streams.atmosphere_240km
stream_list.atmosphere.*
```

The namelist, streams and stream lists must match the installed MPAS Registry and
physics tables.

## 5. Load the runtime and install the packages

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

Minimum command checks:

```bash
command -v mpaswf
command -v mpas-bmatrix || true
PYTHONPATH="$BMATRIX_ROOT/src:${PYTHONPATH:-}" python -m bmatrix --help
```

## 6. Validate the composed configuration

The default runnable case is:

```bash
cd "$BMATRIX_ROOT"
export CONFIG=configs/jaci-x1.10242.yaml
```

It is composed from:

```text
configs/jaci.yaml
configs/jaci-x1.10242.yaml
configs/bmatrix-x1.10242.yaml
configs/bmatrix/x1.10242/*.yaml
```

Resolve and inspect it before submitting any PBS jobs:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix check-config \
  --config "$CONFIG" \
  > "$WORK_ROOT/check-config.json"

less "$WORK_ROOT/check-config.json"
```

Minimum acceptance:

- the command exits with status 0;
- no required path remains as an unresolved `${VARIABLE}` string;
- `project.work_root` points to the intended persistent work area;
- `mesh.name` is `x1.10242`;
- `mesh.nproc` is the intended rank count and a matching partition exists;
- MPAS-JEDI executables and static files resolve to the intended installation;
- the resolved mapping contains `controls`, `bflow`, `vbal`, `unbalance`,
  `hdiag`, `nicas`, `single_observation` and `dirac`;
- `configuration_sources` and `bmatrix_contract_sources` list the expected YAML
  files.

Do not continue until this step is correct.

## 7. Obtain the forecast-pair input

### Route A: generate pairs with `mpaswf`

Select a valid `mpaswf` configuration:

```bash
cd "$MPASWF_ROOT"
export MPASWF_CONFIG=/path/to/mpaswf-config.yaml
```

Run the upstream phases supported by the selected `mpaswf` version:

```bash
mpaswf run --phase prepare  --config "$MPASWF_CONFIG"
mpaswf run --phase init     --config "$MPASWF_CONFIG" --submit --wait
mpaswf run --phase forecast --config "$MPASWF_CONFIG" --submit --wait
mpaswf run --phase manifest --config "$MPASWF_CONFIG"
```

The NMC pair at valid time `T` is:

```text
forecast initialized at T - 48 h, valid at T
minus
forecast initialized at T - 24 h, valid at T
```

Set and inspect the produced manifest:

```bash
export MANIFEST=/path/to/mpaswf-work/products/mpas-forecast-manifest.tsv

test -s "$MANIFEST"
head -n 5 "$MANIFEST"
```

Each row must reference readable f048 and f024 MPAS-JEDI `mpasout` states valid
at the same time.

### Route B: use an existing BFLOW workspace

```bash
export BFLOW="$WORK_ROOT/bmatrix/bflow_preprocessing/np128_<START_VALID>_<END_VALID>"

test -s "$BFLOW/manifest.tsv"
find "$BFLOW/output" -name 'PTB_f48mf24.nc' | sort
find "$BFLOW/output" -name 'FULL_f24.nc' | sort
find "$BFLOW/output" -name 'FULL_f48.nc' | sort
```

When this route is used, start the pipeline at VBAL in Section 10.

## 8. Inspect the execution plan

For Route A:

```bash
cd "$BMATRIX_ROOT"

PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage plots \
  --dry-run \
  | tee "$WORK_ROOT/pipeline-plan.json"
```

Confirm the stage order and workspace roots before launching the workflow.

## 9. Run and validate BFLOW

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage bflow \
  --clean \
  --poll-seconds 30 \
  2>&1 | tee "$WORK_ROOT/bflow-smoke.log"
```

The command output reports the deterministic BFLOW workspace. Export it if not
already known:

```bash
export BFLOW="$WORK_ROOT/bmatrix/bflow_preprocessing/np128_<START_VALID>_<END_VALID>"
```

Validate:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix validate \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --stage bflow
```

Minimum artifacts:

```bash
test -s "$BFLOW/manifest.tsv"
find "$BFLOW/output" -name 'PTB_f48mf24.nc' | sort
find "$BFLOW/output" -name 'FULL_f24.nc' | sort
find "$BFLOW/output" -name 'FULL_f48.nc' | sort
```

## 10. Run VBAL through PLOTS

After BFLOW is valid, run the remaining sequential stages:

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

The orchestrator waits for each PBS dependency and validates a completed stage
before starting the next one.

For debugging, run one stage at a time:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage <stage> \
  --to-stage <stage> \
  --clean \
  --poll-seconds 30
```

## 11. Validate every stage explicitly

```bash
for stage in bflow vbal unbalance hdiag nicas so dirac plots; do
  PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix validate \
    --config "$CONFIG" \
    --bflow-workspace "$BFLOW" \
    --stage "$stage" || break
done
```

Record the first failed stage and do not continue interpreting downstream
products after a failure.

## 12. Minimum artifact checklist

Use `mpas-bmatrix products` to print the reusable final products:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix products \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW"
```

The smoke run should contain at least:

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

UNBALANCE
  samplesUnbalanced/PTB_f48mf24_*.nc

HDIAG
  mpas.stddev.nc
  mpas.cor_rh.nc
  mpas.cor_rv.nc

NICAS
  merge/mpas_nicas.nc
  merge/mpas_nicas_local_*
  merge/mpas_nicas_grids_local_*
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

## 13. Numerical and format checks

Check required NetCDF format where applicable:

```bash
ncdump -k /path/to/product.nc
```

Expected for products requiring CDF5:

```text
cdf5
```

For SO, confirm:

```bash
grep -E 'CostFunction::addIncrement: Analysis|with status = 0' /path/to/SO/run_SO.runlog
```

For native analysis output, verify expected MPAS fields rather than canonical
JEDI names:

```bash
ncdump -h /path/to/SO/an.*.nc | \
  egrep 'uReconstructZonal|uReconstructMeridional|theta|qv|surface_pressure'
```

Do not classify SO as failed solely because selected native `an-bg` fields are
zero; use the OOPS/JEDI log and observation-space outputs.

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

Send the following report back to the maintainer:

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

The most useful report identifies the **first** invalid stage and includes the
resolved configuration plus exact log/product paths.
