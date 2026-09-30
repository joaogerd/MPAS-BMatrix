# Generating NMC forecast pairs with `mpaswf`

This repository starts at the BFLOW boundary. The MPAS forecasts and
same-valid-time NMC pairs must be produced before running the B-matrix stages.
In the validated workflow, that upstream producer is the external repository:

```text
https://github.com/joaogerd/mpaswf
```

`mpaswf` is intentionally MPAS-only. It prepares GFS/WPS inputs, runs
`mpas_init_atmosphere`, integrates MPAS forecasts, and writes a neutral
forecast-pair manifest. It does **not** run BFLOW, BUMP, SABER, MPAS-JEDI
variational tests, observation processing, or plotting.

## 1. Clone both repositories

Use a project root and a work root. The paths below are placeholders.

```bash
export REPOS_ROOT=/path/to/projects
export WORK_ROOT=/path/to/work/MPAS-BMatrix

mkdir -p "$REPOS_ROOT" "$WORK_ROOT"
cd "$REPOS_ROOT"

git clone https://github.com/joaogerd/mpaswf.git
git clone https://github.com/joaogerd/MPAS-BMatrix.git

export MPASWF_ROOT="$REPOS_ROOT/mpaswf"
export BMATRIX_ROOT="$REPOS_ROOT/MPAS-BMatrix"
```

Install the upstream workflow:

```bash
cd "$MPASWF_ROOT"
python -m pip install --no-deps -e .
```

For development of `mpaswf` itself:

```bash
python -m pip install -e '.[dev]'
pytest
```

Install this package in the same environment:

```bash
cd "$BMATRIX_ROOT"
python -m pip install -e .
```

On JACI, load the MPAS-JEDI environment from the B-matrix repository:

```bash
cd "$BMATRIX_ROOT"
export STACK_ROOT=/path/to/spack-stack
source scripts/load_jaci_env.sh
```

## 2. Prepare the `mpaswf` configuration

The configuration belongs to `mpaswf`, not to this repository. Keep it in the
MPAS forecast campaign directory or in the `mpaswf` checkout.

A generic location is:

```bash
MPASWF_CONFIG=/path/to/mpaswf-config.yaml
MPASWF_WORK=/path/to/mpaswf-work
```

The important scientific campaign fields are:

```yaml
campaign:
  start_valid_time: "2026-06-22T00:00:00Z"
  end_valid_time: "2026-06-25T00:00:00Z"
  interval_hours: 24
  leads_hours: [24, 48]
```

For each valid time, `mpaswf` will generate the two forecasts needed by the NMC
method:

```text
valid time T:
  f048 initialized at T - 48 h
  f024 initialized at T - 24 h
  NMC pair = f048(T) - f024(T)
```

The full `mpaswf` configuration also declares paths, executables, GFS/WPS
templates, MPAS namelist/stream templates, static mesh products, execution
backend, PBS settings, and validation rules. The static section describes the
generated MPAS static product. Fixed mesh, partition, invariant, table, and
support files are links; the generated `x1.10242.static.nc` must not be listed as
an input link.

## 3. Run the upstream MPAS workflow

Run the phases in order from the `mpaswf` checkout.

### Prepare GFS/WPS inputs

```bash
cd "$MPASWF_ROOT"
mpaswf run --phase prepare --config "$MPASWF_CONFIG"
```

This phase reuses existing GFS files when present, downloads missing files when a
URL template is configured, and runs WPS `link_grib`/`ungrib` to create the
`FILE:YYYY-MM-DD_HH` inputs.

### Generate MPAS initial conditions

For PBS execution, the static interpolation may be a dependency boundary. The
robust campaign pattern is:

```bash
# Render or submit the one-time static interpolation if it is missing.
mpaswf run --phase init --config "$MPASWF_CONFIG" --submit

# After the static job completes, rerun init to submit dynamic initializations.
mpaswf run --phase init --config "$MPASWF_CONFIG" --submit
```

For small smoke tests, or when it is safe to block the terminal until PBS
completion:

```bash
mpaswf run --phase init --config "$MPASWF_CONFIG" --submit --wait
```

The init phase generates or reuses the mesh-level static product and then
generates one date-dependent MPAS initial state for each required initialization
time.

### Run f024/f048 MPAS forecasts

```bash
mpaswf run --phase forecast --config "$MPASWF_CONFIG" --submit --wait
```

For larger campaigns, omit `--wait` and monitor PBS manually:

```bash
mpaswf run --phase forecast --config "$MPASWF_CONFIG" --submit
```

The forecast phase produces both `restart` and `da_state` products for the
f024/f048 forecasts.

### Write the pair manifest

```bash
mpaswf run --phase manifest --config "$MPASWF_CONFIG"
```

The manifest is written to:

```text
<mpaswf work_dir>/products/mpas-forecast-manifest.tsv
```

Its columns are:

```text
valid_time    f048_state    f024_state    f048_restart    f024_restart
```

This file is the hand-off between `mpaswf` and `MPAS-BMatrix`.

Current `mpaswf` also writes `mpas-forecast-manifest.json` beside the TSV.
That sidecar declares the versioned `monan-nmc-forecast-pairs-v1` contract and
contains the producer/consumer identity, exact TSV columns, pair semantics,
pair count and SHA-256 of the TSV. `mpas-bmatrix check-manifest` verifies the
sidecar automatically when present and rejects a mismatched/stale pair.

A historical TSV without the JSON sidecar remains accepted during migration;
in that case the validation report sets `producer_contract_verified: false`.
Newly generated campaigns should always carry both files.\n\n### Scientific preflight\n\nThe hand-off is not usable merely because the files exist. With the normal `--config`, `mpas-bmatrix check-manifest --config <config>` and manifest-driven BFLOW execution open every f048/f024 `da_state` before workspace creation or BFLOW/ESMF work. Plain `check-manifest` remains a lightweight producer-manifest check. They verify the BFLOW-required MPAS variables, `Time`/`nCells`/`nVertLevels`, `xtime` against manifest `valid_time`, pairwise grid compatibility, and campaign-wide grid consistency.\n\nThe required variables are derived from `bflow.wind_transform`, `bflow.copy_variables` and `bflow.derived_variables`. They are intentionally not duplicated in mpaswf; the MPAS-BMatrix scientific YAML remains the source of truth.

## 4. Use the `mpaswf` manifest in this package

After `mpaswf` produces the manifest, return to this repository:

```bash
cd "$BMATRIX_ROOT"
source scripts/load_jaci_env.sh

CONFIG=configs/jaci-x1.10242.yaml
MANIFEST=<mpaswf work_dir>/products/mpas-forecast-manifest.tsv
```

Build the B-matrix from the upstream MPAS forecast pairs:

```bash
mpas-bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage plots \
  --clean \
  --poll-seconds 30
```

For debugging only BFLOW from the manifest:

```bash
mpas-bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage bflow \
  --clean \
  --poll-seconds 30
```

Once BFLOW is complete, later reruns may use the deterministic or explicit BFLOW
workspace instead of the manifest:

```bash
BFLOW="$WORK_ROOT/bmatrix/bflow_preprocessing/np128_<START_VALID>_<END_VALID>"

mpas-bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage vbal \
  --to-stage plots \
  --clean \
  --poll-seconds 30
```

## 5. Operational contract

Maintain this separation between repositories:

```text
mpaswf
  owns GFS/WPS, MPAS initialization, MPAS forecasts and pair manifest

MPAS-BMatrix
  owns BFLOW, VBAL, UNBALANCE, HDIAG, NICAS, SO, DIRAC and PLOTS
```

Do not add GFS download, WPS, `mpas_init_atmosphere`, or MPAS forecast
integration logic to this repository unless the project boundary is intentionally
redesigned.


### Mesh identity

Scientific preflight compares every state against the configured canonical `mesh.grid` using `latCell` and `lonCell`. Equal `nCells` is not sufficient. The report records `mesh.name` and a SHA-256 fingerprint of canonical cell geometry. The fingerprint hashes only the coordinate arrays, not the full forecast state, so atmospheric fields are not reread merely to identify the mesh.


#### Why dimensions are not a mesh identity

Two MPAS meshes may have the same `nCells` and `nVertLevels` while assigning cells to different geographic coordinates. For that reason, dimensions remain structural checks only. The authoritative identity for a B-matrix case is the configured `mesh.grid`; forecast states must reproduce its cell-center geometry within a strict representation tolerance. `mpaswf` does not need to know this consumer-side scientific choice.


### Vertical grid is case configuration, not a hard-coded constant

`mesh.nvertlevels` declares the total model-level count for the selected case. The current x1.10242 JACI case declares 55 because that is the present configuration; **55 is not an ecosystem invariant**. A future MONAN configuration with 100+ levels must declare its own value and the same code path will validate it.

Scientific preflight requires every f048/f024 state to expose `nVertLevels` equal to the case declaration. NICAS also consumes the explicit declaration when converting `dirac_level_from_top`; there is no implicit 55-level fallback.

This count proves vertical-size compatibility, not full vertical-coordinate identity. Parameters such as `vbal.sampling.reduced levels` remain separate scientific choices: they may equal the full model level count for a given experiment, but they are not aliases for `mesh.nvertlevels` and must not be silently synchronized.
