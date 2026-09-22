# End-to-end tutorial: MPAS forecasts to static B-matrix

This is the operational, sequential tutorial for a first complete
`MPAS-BMatrix` run. A user should be able to start here and reach the final
B-matrix diagnostics without opening another document to discover a mandatory
command.

The validated JACI/x1.10242 smoke path is:

```text
environment
    |
    v
mpaswf: GFS/WPS -> MPAS init -> f024/f048 forecasts -> pair manifest
    |
    v
MPAS-BMatrix: BFLOW -> VBAL -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

This smoke run verifies the software, environment, scheduler, file contracts and
stage interfaces. The shipped `mpaswf` campaign currently provides four
same-valid-time NMC pairs, which is sufficient for the software smoke test but
not a scientifically converged production B-matrix.

For installation background, configuration reference, theory and troubleshooting
see the linked specialist documents. Those pages are optional while following
this tutorial.

## 1. What is required before starting

The JACI example assumes:

- a JACI account with access to the project filesystem and PBS queues;
- `git`, the JACI Anaconda module and network/data access required by the
  configured GFS acquisition;
- a MONAN-JEDI installation exposing MPAS, WPS and JEDI executables;
- the x1.10242 mesh, 128-way partition and validated tutorial static/runtime
  files at the paths declared by the shipped JACI YAMLs;
- a validated spack-stack checkout that can be read from login and compute
  nodes.

JACI paths beginning with `/p/projetos/monan_das/...` are site-specific
examples. On another machine, keep the same logical sequence but provide an
equivalent site configuration.

The production responsibility boundary is important:

```text
mpaswf
  owns GFS/WPS, MPAS initialization, MPAS forecasts and pair manifest

MPAS-BMatrix
  owns BFLOW, VBAL, HDIAG, NICAS, SO, DIRAC and PLOTS
```

There is no production UNBALANCE stage. HDIAG reads the original centered NMC
perturbations and applies inverse `BUMP_VerticalBalance` in memory.

## 2. Start from a clean JACI shell

Do not reuse a shell in which another Conda environment or a different
spack-stack was already loaded.

Make Conda available:

```bash
module load anaconda
start_conda
```

Create the Python environment once:

```bash
conda create -n monan-jedi-bmatrix -c conda-forge \
  python=3.11 pip \
  pyyaml numpy=1.26 netcdf4 cftime xarray matplotlib \
  esmpy windspharm pytest ruff -y
```

On every new JACI login, initialize Conda again and then activate the existing
environment:

```bash
module load anaconda
start_conda
conda activate monan-jedi-bmatrix
```

Creating the environment is a one-time operation; initializing Conda with
`module load anaconda` + `start_conda` is required again in a fresh JACI
shell.

For more detail about the Python/spack-stack isolation strategy, see
[Installation on JACI](install-jaci.md).

### Checkpoint 1 -- Python environment

```bash
command -v python
python -c "import sys, numpy; print(sys.version); print(sys.executable); print(numpy.__file__)"
```

Expected: Python 3.11 and NumPy from the same
`monan-jedi-bmatrix` Conda environment.

## 3. Define all roots before they are used

The following layout is the maintained JACI example:

```bash
export PROJECT_ROOT="/p/projetos/monan_das/$USER/projects"
export WORK_ROOT="/p/projetos/monan_das/$USER/work/MPAS-BMatrix"
export MPASWF_WORK="/p/projetos/monan_das/$USER/work/mpaswf"

export BMATRIX_ROOT="$PROJECT_ROOT/MPAS-BMatrix"
export MPASWF_ROOT="$PROJECT_ROOT/mpaswf"

export MONAN_JEDI_INSTALL_ROOT="/p/projetos/monan_das/$USER/build/monan-jedi"

# Select the validated spack-stack checkout available to your JACI account.
# This is a site/runtime input, not a value owned by MPAS-BMatrix.
export STACK_ROOT="/path/to/validated/spack-stack"

mkdir -p "$PROJECT_ROOT" "$WORK_ROOT"
```

`PROJECT_ROOT` stores source checkouts. `WORK_ROOT` is the MPAS-BMatrix
calibration/work root. `MPASWF_WORK` is the upstream forecast-work root.
`MONAN_JEDI_INSTALL_ROOT` is the installed runtime prefix, not a source
checkout. `STACK_ROOT` selects the dependency/MPI environment used both
interactively and in generated PBS jobs.

The current MPAS-BMatrix JACI base maps
`environment.variables.STACK_ROOT` to the exported `STACK_ROOT`, so the
selected stack is explicit rather than embedded as a personal path.

### Checkpoint 2 -- external runtime roots

```bash
test -d "$STACK_ROOT" || { echo "Missing STACK_ROOT: $STACK_ROOT"; exit 1; }
test -x "$MONAN_JEDI_INSTALL_ROOT/bin/mpas_init_atmosphere" || exit 1
test -x "$MONAN_JEDI_INSTALL_ROOT/bin/mpas_atmosphere" || exit 1
test -x "$MONAN_JEDI_INSTALL_ROOT/bin/ungrib.exe" || exit 1
test -x "$MONAN_JEDI_INSTALL_ROOT/bin/link_grib.csh" || exit 1
test -x "$MONAN_JEDI_INSTALL_ROOT/bin/mpasjedi_error_covariance_toolbox.x" || exit 1
test -x "$MONAN_JEDI_INSTALL_ROOT/bin/mpasjedi_variational.x" || exit 1
test -f "$MONAN_JEDI_INSTALL_ROOT/share/wps/Variable_Tables/Vtable.GFS" || exit 1
```

The legacy `mpasjedi_unbalance_ensemble.x` executable is not required by the
production stage graph.

## 4. Obtain and install both workflow repositories

Clone only when the checkout is absent:

```bash
test -d "$MPASWF_ROOT/.git" || \
  git clone https://github.com/joaogerd/mpaswf.git "$MPASWF_ROOT"

test -d "$BMATRIX_ROOT/.git" || \
  git clone https://github.com/joaogerd/MPAS-BMatrix.git "$BMATRIX_ROOT"
```

Install both public commands into the same active Conda environment:

```bash
python -m pip install --no-deps -e "$MPASWF_ROOT"
python -m pip install -e "$BMATRIX_ROOT"

mpaswf --help >/dev/null
mpas-bmatrix --help >/dev/null
```

Normal execution uses `mpaswf` and `mpas-bmatrix` directly. Do not set
`PYTHONPATH` and do not replace these commands with `python -m bmatrix`.

Record the revisions used by the run:

```bash
git -C "$MPASWF_ROOT" rev-parse HEAD
git -C "$BMATRIX_ROOT" rev-parse HEAD
```

## 5. Load the JACI scientific environment

```bash
module load anaconda
start_conda
conda activate monan-jedi-bmatrix

cd "$BMATRIX_ROOT"
source scripts/load_jaci_env.sh
```

The loader makes the compiled scientific runtime available while restoring the
Conda Python command and removing spack-stack Python search paths.

Verify the result:

```bash
command -v python
command -v mpaswf
command -v mpas-bmatrix
python -c "import sys, numpy; print(sys.executable); print(numpy.__file__)"
```

Expected:

- `python`, `mpaswf` and `mpas-bmatrix` resolve through the active Conda
  environment;
- NumPy is loaded from a path below `$CONDA_PREFIX`;
- `PYTHONPATH` is not set after `load_jaci_env.sh`.

The loader now removes Python search paths injected by spack-stack
unconditionally. If a Conda environment was already active, it also verifies
that both Python and NumPy belong to that environment and fails immediately if
they are mixed.

A direct checkpoint is:

```bash
printf 'CONDA_PREFIX=%s\n' "$CONDA_PREFIX"
printf 'PYTHONPATH=%s\n' "${PYTHONPATH:-<not set>}"
python -c "import sys, numpy; print('python =', sys.executable); print('numpy  =', numpy.__file__)"
```

For the supported Conda workflow, both printed paths must begin with
`$CONDA_PREFIX`, and `PYTHONPATH` must print `<not set>`.

## 6. Inspect the two JACI configurations

There are two independent configuration entry points:

```bash
export MPASWF_CONFIG="$MPASWF_ROOT/configs/jaci-x1.10242.yaml"
export CONFIG="$BMATRIX_ROOT/configs/jaci-x1.10242.yaml"
```

### 6.1 MPASWF configuration

The upstream JACI YAML owns:

- MONAN-JEDI software root;
- `paths.work_dir`, GFS cache and template directory;
- x1.10242 invariant/mesh/partition inputs;
- PBS resources and compute-node bootstrap.

The shipped paths use `$USER` where the data are expected to be user-local.
The maintained bootstrap uses `${STACK_ROOT}`, so selecting another validated
stack requires changing the environment variable rather than editing a user
name into the YAML.

Inspect the fields that are most likely to vary:

```bash
grep -nE 'monan_jedi_root:|work_dir:|gfs_dir:|source:|bootstrap:|STACK_ROOT' \
  "$MPASWF_CONFIG"
```

Do not modify paths merely because they are configurable. Change them only when
the declared resource does not exist or your site layout differs.

### 6.2 MPAS-BMatrix configuration

The runnable B-matrix entry point composes:

```text
configs/jaci.yaml
  + configs/jaci-x1.10242.yaml
  + configs/bmatrix-x1.10242.yaml
  + configs/bmatrix/x1.10242/*.yaml
```

The shipped x1.10242 case already declares the mesh, 128-way partition,
validated invariant/tutorial files and scientific stage contracts.

Resolve and audit the effective configuration before any B-matrix jobs:

```bash
mkdir -p "$WORK_ROOT"

mpas-bmatrix check-config \
  --config "$CONFIG" > "$WORK_ROOT/check-config.json"

python -m json.tool "$WORK_ROOT/check-config.json" >/dev/null
```

Minimum acceptance:

- no unresolved environment variables;
- `project.work_root` is the intended JACI work area;
- `mesh.nproc` is 128 for this reference case;
- MONAN-JEDI runtime paths resolve under `MONAN_JEDI_INSTALL_ROOT`;
- `environment.variables.STACK_ROOT` resolves to the selected stack;
- the scientific sections `controls`, `bflow`, `vbal`, `hdiag`,
  `nicas`, `single_observation` and `dirac` are present.

For the complete configuration contract, see [Configuration](configuration.md).

## 7. Generate MPAS forecasts with MPASWF -- Path A

This is the normal first-run path. Skip to Section 11 (Path B) only when a
completed BFLOW workspace already exists.

### 7.1 Validate PBS/MPI before a long job

```bash
cd "$MPASWF_ROOT"
mpaswf pbs-smoke --config "$MPASWF_CONFIG"
```

`pbs-smoke` is the correct command name. It submits a real one-rank PBS job
and verifies compute-node execution and shared-filesystem visibility.

### 7.2 Prepare GFS/WPS inputs

```bash
mpaswf run --phase prepare --config "$MPASWF_CONFIG"
```

Input -> processing -> output:

```text
GFS f000
  -> link_grib/ungrib
  -> per-initialization WPS GFS:YYYY-MM-DD_HH products
```

Existing valid local GFS files are reused. With the shipped campaign contract,
missing files may be downloaded through the configured NOAA URL.

### 7.3 Create/reuse static data and MPAS initial states

```bash
mpaswf run --phase init \
  --config "$MPASWF_CONFIG" \
  --submit \
  --wait
```

With `--submit --wait`, the command waits for the static dependency when it
must be generated and then processes the date-dependent initial states. The
shipped JACI case normally reuses its configured precomputed invariant.

For a large campaign where you intentionally omit `--wait`, a missing static
product forms a dependency boundary: the first `init --submit` may submit only
the static job. After that job is valid, run the same init command again to
submit the date-dependent initializations.

### 7.4 Run the f024/f048 forecasts

```bash
mpaswf run --phase forecast \
  --config "$MPASWF_CONFIG" \
  --submit \
  --wait
```

For every configured valid time `T`, MPASWF produces:

```text
f048 initialized at T - 48 h -> valid at T
f024 initialized at T - 24 h -> valid at T
```

`--wait` keeps the command attached to PBS status until the submitted jobs
finish and their expected products validate. Without `--wait`, the command
returns after submission and the user must monitor PBS before continuing.

### 7.5 Create the neutral forecast-pair manifest

```bash
mpaswf run --phase manifest --config "$MPASWF_CONFIG"
```

This phase does not submit PBS. It validates all required f024/f048 products and
writes:

```text
<mpaswf work_dir>/products/mpas-forecast-manifest.tsv
```

For the shipped JACI config:

```bash
export MANIFEST="$MPASWF_WORK/products/mpas-forecast-manifest.tsv"
```

The current columns are:

```text
valid_time    f048_state    f024_state    f048_restart    f024_restart
```

BFLOW consumes the `f048_state` and `f024_state` paths. Restart columns are
retained by the producer but are not BFLOW inputs.

### Checkpoint 3 -- forecast manifest

```bash
test -s "$MANIFEST" || {
  echo "Manifest not found or empty: $MANIFEST"
  exit 1
}

head "$MANIFEST"
mpas-bmatrix check-manifest --manifest "$MANIFEST"
```

Do not continue if `check-manifest` fails. The B-matrix code requires at least
four valid pairs for the maintained smoke workflow and verifies that referenced
state files exist.

For more detail about the producer/consumer boundary, see
[Generating NMC forecast pairs with mpaswf](mpaswf-pairs.md).

## 8. Plan the complete B-matrix run and discover BFLOW

**Pre-condition:** `MANIFEST` is valid.

A BFLOW workspace is not an input directory that a first-time user must create.
When starting from the manifest, `mpas-bmatrix` derives its deterministic path
and creates it when BFLOW runs.

Generate a side-effect-free plan:

```bash
mpas-bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage plots \
  --dry-run > "$WORK_ROOT/pipeline-plan.json"
```

Read the deterministic BFLOW path directly from that plan:

```bash
export BFLOW="$(
  python - "$WORK_ROOT/pipeline-plan.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    print(json.load(stream)["workspaces"]["bflow"])
PY
)"

printf 'BFLOW=%s\n' "$BFLOW"
```

Do **not** run `mkdir -p "$BFLOW"` for Path A. The BFLOW preparation code
creates the workspace, its input links, internal manifest, logs and output
directories.

### Checkpoint 4 -- execution plan

```bash
python - "$WORK_ROOT/pipeline-plan.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    plan = json.load(stream)

expected = ["bflow", "vbal", "hdiag", "nicas", "so", "dirac", "plots"]
assert plan["stages"] == expected, plan["stages"]
print("Stages:", " -> ".join(plan["stages"]))
print("BFLOW:", plan["workspaces"]["bflow"])
PY
```

Expected:

```text
bflow -> vbal -> hdiag -> nicas -> so -> dirac -> plots
```

There must be no production `unbalance` stage.

## 9. Run BFLOW through PLOTS

The orchestrator can execute the entire production graph in one call:

```bash
mpas-bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage plots \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean \
  --poll-seconds 30 \
  2>&1 | tee "$WORK_ROOT/bmatrix-end-to-end.log"
```

Stage contract:

```text
MPAS f048/f024 states
        |
        v
BFLOW
  FULL_f48 + FULL_f24 + centered PTB_f48mf24
        |
        v
VBAL
  vertical-balance and sampling coefficients
        |
        v
HDIAG
  original PTB samples + inverse VBAL in memory
  -> stddev + horizontal/vertical correlation diagnostics
        |
        v
NICAS
  compressed spatial correlation operator
        |
        +-------------------+
        |                   |
        v                   v
SO validation          DIRAC validation
        \                   /
         \                 /
          v               v
               PLOTS
```

For scheduler-backed stages, `mpas-bmatrix build` submits the generated PBS
job, waits for it, validates its products and only then starts the dependent
stage. `--poll-seconds 30` controls scheduler polling; it does not change the
scientific calculation.

If a stage fails, stop at the first failed stage. Inspect that stage workspace
for generated YAML/PBS files and `stdout.log`, `stderr.log` or the
stage-specific runlog before rerunning downstream work.

## 10. Validate the completed run

Validate every production stage without rerunning it:

```bash
for stage in bflow vbal hdiag nicas so dirac plots; do
  mpas-bmatrix validate \
    --config "$CONFIG" \
    --bflow-workspace "$BFLOW" \
    --stage "$stage" || exit 1
done
```

Ask the CLI for the resolved reusable final products:

```bash
mpas-bmatrix products \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  | tee "$WORK_ROOT/final-products.json"
```

### Checkpoint 5 -- BFLOW and final products

BFLOW itself must contain:

```bash
test -s "$BFLOW/manifest.tsv" || exit 1

find "$BFLOW/output" -name 'FULL_f24.nc' | sort
find "$BFLOW/output" -name 'FULL_f48.nc' | sort
find "$BFLOW/output" -name 'PTB_f48mf24.nc' | sort
```

The complete run should additionally validate products equivalent to:

```text
VBAL
  mpas_vbal.nc
  mpas_sampling.nc
  rank-local VBAL/sampling products
  samples/PTB_f48mf24_*.nc

HDIAG
  mpas.stddev.nc
  mpas.cor_rh.nc
  mpas.cor_rv.nc

NICAS
  merge/mpas_nicas.nc
  rank-local/grid products
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

No `samplesUnbalanced` directory is required for the production workflow.

A successful smoke test means the complete operational chain executed and its
validators accepted the expected products. It does not by itself establish that
four NMC samples provide production-quality covariance statistics.

## 11. Path B -- resume from an existing BFLOW workspace

Use this path only when BFLOW has already been completed by a previous run.

Set the real existing directory; do not create an empty replacement:

```bash
export BFLOW="/path/to/existing/bflow_preprocessing/np128_YYYYMMDDHH_YYYYMMDDHH"
```

**Pre-condition:** the workspace already contains its internal manifest and
completed BFLOW products.

```bash
test -s "$BFLOW/manifest.tsv" || {
  echo "Existing BFLOW manifest not found: $BFLOW/manifest.tsv"
  exit 1
}

find "$BFLOW/output" -name 'PTB_f48mf24.nc' | sort

mpas-bmatrix validate \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --stage bflow
```

Only after that validation succeeds, resume downstream:

```bash
mpas-bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage vbal \
  --to-stage plots \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean \
  --poll-seconds 30
```

Path B does not need the original external MPASWF manifest on the command line:
the existing BFLOW workspace already owns a normalized internal
`manifest.tsv`.

## 12. What normally needs user configuration

For the maintained JACI/x1.10242 example, do not edit every YAML value. Most
scientific settings are intentionally versioned defaults.

| Setting | Required to change? | Purpose |
| --- | --- | --- |
| `MONAN_JEDI_INSTALL_ROOT` | yes, if your install prefix differs | Public MONAN-JEDI runtime root |
| `STACK_ROOT` | yes, select a validated checkout | spack-stack/JEDI dependency environment for login and PBS |
| `PROJECT_ROOT`, `WORK_ROOT` | only if using another storage layout | Source and MPAS-BMatrix work roots |
| MPASWF `paths.*` | only if the shipped JACI layout is not valid | Forecast/GFS/template work areas |
| MPASWF campaign dates | only for another experiment | Valid-time range and NMC pair production |
| x1.10242 mesh/static paths | only if data live elsewhere | Mesh, partition and validated runtime inputs |
| `mesh.nproc` | only with a compatible partition/resource change | MPI size used by B-matrix jobs |
| B-matrix scientific fragments | only for a deliberate scientific experiment | BFLOW/VBAL/HDIAG/NICAS/SO/DIRAC contract |

The current MPAS-BMatrix config does **not** consume shell variables named
`MPAS_MESH_ROOT` or `MPAS_JEDI_STATIC_ROOT`; its shipped mesh/static paths
are explicit in `configs/jaci-x1.10242.yaml`.

For all keys and rebuild boundaries, see [Configuration](configuration.md).

## 13. Quick Start for experienced users

This condensed sequence assumes the Conda environment and both repositories are
already installed and the shipped JACI paths are valid:

```bash
conda activate monan-jedi-bmatrix

export PROJECT_ROOT="/p/projetos/monan_das/$USER/projects"
export WORK_ROOT="/p/projetos/monan_das/$USER/work/MPAS-BMatrix"
export MPASWF_WORK="/p/projetos/monan_das/$USER/work/mpaswf"
export BMATRIX_ROOT="$PROJECT_ROOT/MPAS-BMatrix"
export MPASWF_ROOT="$PROJECT_ROOT/mpaswf"
export MONAN_JEDI_INSTALL_ROOT="/p/projetos/monan_das/$USER/build/monan-jedi"
export STACK_ROOT="/path/to/validated/spack-stack"

export MPASWF_CONFIG="$MPASWF_ROOT/configs/jaci-x1.10242.yaml"
export CONFIG="$BMATRIX_ROOT/configs/jaci-x1.10242.yaml"
export MANIFEST="$MPASWF_WORK/products/mpas-forecast-manifest.tsv"

cd "$BMATRIX_ROOT"
source scripts/load_jaci_env.sh
mpas-bmatrix check-config --config "$CONFIG" >/dev/null

cd "$MPASWF_ROOT"
mpaswf pbs-smoke --config "$MPASWF_CONFIG"
mpaswf run --phase prepare --config "$MPASWF_CONFIG"
mpaswf run --phase init --config "$MPASWF_CONFIG" --submit --wait
mpaswf run --phase forecast --config "$MPASWF_CONFIG" --submit --wait
mpaswf run --phase manifest --config "$MPASWF_CONFIG"

mpas-bmatrix check-manifest --manifest "$MANIFEST"

cd "$BMATRIX_ROOT"
mpas-bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage plots \
  --clean \
  --poll-seconds 30
```

Use the full tutorial, not this abbreviated section, when any checkpoint fails.

## 14. Reproducibility record

For each test or production run, record:

```text
tester:
machine/login node:
MPAS-BMatrix commit:
mpaswf commit:
MPASWF_CONFIG:
CONFIG:
MONAN_JEDI_INSTALL_ROOT:
STACK_ROOT:
mpaswf manifest:
BFLOW workspace:
stage range:
PBS job IDs:
main log:
final product paths:
validation result:
```

## 15. Failure report

Report the first invalid stage rather than only the final missing file:

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
Last relevant log lines:
Expected artifact missing or invalid:
Resolved path/value suspected:
Additional observations:
```

For known runtime and BUMP/NICAS failure modes, see [Operations](operations.md).
For product-level acceptance criteria, see [Stage products](stage-products.md).
For the retained legacy A/B comparison only, see
[In-memory VBAL/HDIAG migration](in-memory-vbal-hdiag.md).
