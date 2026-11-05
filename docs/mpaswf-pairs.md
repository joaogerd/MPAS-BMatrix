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
Newly generated campaigns should always carry both files.

### Scientific preflight

The hand-off is not usable merely because the files exist. With the normal `--config`, `mpas-bmatrix check-manifest --config <config>` and manifest-driven BFLOW execution open every f048/f024 `da_state` before workspace creation or BFLOW/ESMF work. Plain `check-manifest` remains a lightweight producer-manifest check. They verify the BFLOW-required MPAS variables, `Time`/`nCells`/`nVertLevels`, `xtime` against manifest `valid_time`, pairwise grid compatibility, and campaign-wide grid consistency.

The required variables are derived from `bflow.wind_transform`, `bflow.copy_variables` and `bflow.derived_variables`. They are intentionally not duplicated in mpaswf; the MPAS-BMatrix scientific YAML remains the source of truth.

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

Scientific preflight reads the configured canonical `mesh.grid`, which must
contain `latCell` and `lonCell`, and records its SHA-256 geometry fingerprint.
Every state must have a matching `nCells`. When both coordinates are published
in a state, they must match the canonical geometry and the state report records
`state_proof: state-coordinates-match-case-grid` and
`state_geometry_verified: true`. A state with only one coordinate is rejected.

The pinned MPAS native immutable `da_state` stream does not publish either
coordinate. Such states are supported and record
`state_proof: case-grid-plus-cell-count` and `state_geometry_verified: false`.
The fingerprint in their report belongs to the configured grid, not the state.
The campaign-level `mesh_identity.state_geometry_verified` is true only when
all f048/f024 states provide directly matching coordinates.


#### Why dimensions are not a mesh identity

Two MPAS meshes may have the same `nCells` and `nVertLevels` with different
geometry or cell ordering. For states without coordinates, the report therefore
proves only structural compatibility with the declared case. The operator must
ensure that the campaign was generated with that case's mesh; changing
`mesh.grid` after production is not proof of the state's origin. Checks of
required fields, valid time and vertical levels still apply. This limited
evidence is explicit, just as it is for states that omit `zgrid`.


### Vertical grid is case configuration, not a hard-coded constant

`mesh.nvertlevels` declares the total model-level count for the selected case. The current x1.10242 JACI case declares 55 because that is the present configuration; **55 is not an ecosystem invariant**. A future MONAN configuration with 100+ levels must declare its own value and the same code path will validate it.

Scientific preflight requires every f048/f024 state to expose `nVertLevels` equal to the case declaration. NICAS also consumes the explicit declaration when converting `dirac_level_from_top`; there is no implicit 55-level fallback.

This count proves vertical-size compatibility, not full vertical-coordinate identity. Parameters such as `vbal.sampling.reduced levels` remain separate scientific choices: they may equal the full model level count for a given experiment, but they are not aliases for `mesh.nvertlevels` and must not be silently synchronized.


### Vertical-coordinate identity

Equal `nVertLevels` proves only vertical array compatibility. The case's authoritative vertical-coordinate identity is taken from `static.invariant:zgrid`, the MPAS geometric height of layer interfaces. Preflight requires its `nVertLevelsP1` interface count to equal `mesh.nvertlevels + 1` and records a SHA-256 fingerprint of the canonical `zgrid` values.

When an NMC `da_state` itself contains `zgrid`, it is compared directly with the invariant and the report records a direct proof. When the DA stream does not publish `zgrid`, the report deliberately records the weaker proof `case-invariant-plus-level-count`: the state has the configured number of levels, while vertical-coordinate identity comes from the case invariant. This distinction prevents the validation report from claiming evidence that is absent from the state file.

A future 100+ level MONAN configuration therefore requires no code change: provide the corresponding `mesh.nvertlevels` and compatible `static.invariant`; its own `zgrid` fingerprint becomes the vertical identity.

## Forecast discovery: producer manifest first

Use `mpas-bmatrix build --config case.yaml --manifest /path/manifest.tsv`
for MPASWF-generated input forecasts. This is the supported, versioned
producer-consumer interface. MPAS-BMatrix does not need to know the MPASWF
scheduler, output workspace, or naming convention.

If a standalone source does not produce manifests, date-range builds may
use an **explicit case-level path template**:

```yaml
bflow:
  forecast_state_template: "/my/archive/{mesh_name}/{init_compact}/f{lead_padded}/state_dt{dt}.nc"
```

Supported placeholders:

| Key | Meaning |
| --- | --- |
| `mesh_name` | `mesh.name` |
| `nproc` | selected `mesh.nproc` |
| `dt` | `--dt` or `runtime.config_dt`, seconds |
| `lead_hours` / `lead_padded` | lead in hours, integer / zero-padded 3 digit string |
| `init_time` | `YYYY-MM-DD_HH:MM:SS` |
| `init_compact` | `YYYYMMDDHH` |
| `init_date_file` | `YYYY-MM-DD_HH.MM.SS` |
| `valid_time` | `YYYY-MM-DD_HH:MM:SS` |
| `valid_compact` | `YYYYMMDDHH` |
| `valid_date_file` | `YYYY-MM-DD_HH.MM.SS` |

Relative templates are based at `project.work_root`. Without a manifest or
this explicitly selected filename pattern, the application stops with an
actionable error. It does **not** guess an original tutorial directory.

Automatic BFLOW workspace paths now always include the mesh identifier.
For a supplied manifest they also contain a short SHA-256 fingerprint of the
manifest *contents*; campaigns sharing start/end dates but different
intermediate inputs therefore do not silently reuse one workspace. Selecting
`--bflow-workspace` explicitly retains responsibility for isolating that
workspace.

This is still the v1 NMC contract: the producer manifest has f048/f024
products. Other lead pairs require a versioned producer-consumer change.


## Scientific dimension validation during NMC differencing

Before writing a perturbation, BFLOW compares the names, sizes and numeric
representations of every common scientific field in the older and newer
forecast states. Char-valued time/metadata variables are not perturbations.
A numeric field that exists in both forecasts but has a different mesh,
number of vertical levels, axis order or numeric/non-numeric type now fails
with the field name and dimensions rather than being silently omitted.
This check complements the canonical mesh preflight and prevents accidental
calibration from incomplete NMC perturbation samples.

## NMC producer/consumer contract v2: configurable forecast leads

The legacy `monan-nmc-forecast-pairs-v1` protocol, with
`f048_state/f024_state`, is fully supported for existing campaigns.

For a new two-lead NMC scientific configuration, MPASWF now emits a
**versioned v2** TSV and adjacent JSON sidecar. The TSV fields are:

```text
valid_time  older_lead_hours  newer_lead_hours  older_state  newer_state  older_restart  newer_restart
```

The columns are TAB-separated. The two state paths are the actual MPAS
DA-state files; the restart paths are provided for provenance and are not
used as BFLOW perturbation inputs. A v2 row always has
`older_lead_hours > newer_lead_hours > 0`; every row of one campaign must
use the same lead pair.

Set the BMatrix scientific configuration to those exact durations:

```yaml
bflow:
  nmc:
    older_lead_hours: 36
    newer_lead_hours: 12
```

Then run, for example,

```bash
mpas-bmatrix check-manifest --config case.yaml --manifest /archive/mpas-forecast-manifest.tsv
mpas-bmatrix build --config case.yaml --manifest /archive/mpas-forecast-manifest.tsv --from-stage bflow --to-stage dirac
```

The BMatrix reader verifies the producer sidecar (schema/columns,
producer/consumer identity, actual lead pair, pair count and SHA-256) and
then checks the forecast times and mesh/vertical geometry in NetCDF. It
rejects conflicting YAML lead settings rather than silently treating a
36-hour forecast as f048.

The BFLOW workspace manifest and input links preserve actual lead
durations (`f036.nc`, `f012.nc` for 36/12). The legacy pair retains its
historical `f048.nc` and `f024.nc` links for compatibility. Relative
paths in a producer manifest are resolved against that manifest's
directory, not the shell's current directory.

Both producer and consumer have synthetic regression tests for the v1
and v2 contracts, including invalid lead pairs, tampering, missing
sidecars, incompatible model grids and changes in sample periods.

**Scientific limitation:** Any older/newer pair implements an NMC
difference; statistical representativeness, covariance length scales and
other calibrated B parameters remain scientific decisions that must be
validated with the selected dataset. This change does not eliminate the
minimum sample count, SABER/BUMP runtime dependencies or the need for
full JACI numerical regression testing.
