# Workflow

This document describes the operational flow represented by the `main` branch.

## 0. Checkout layout

Use generic roots and adapt only these exports to the local system:

```bash
export PROJECT_ROOT=/path/to/projects
export WORK_ROOT=/path/to/work/MPAS-BMatrix

mkdir -p "$PROJECT_ROOT" "$WORK_ROOT"
cd "$PROJECT_ROOT"

git clone https://github.com/joaogerd/MPAS-BMatrix.git
git clone https://github.com/joaogerd/mpaswf.git

export BMATRIX_ROOT="$PROJECT_ROOT/MPAS-BMatrix"
export MPASWF_ROOT="$PROJECT_ROOT/mpaswf"
```

Install the repositories in the active Python environment:

```bash
python -m pip install --no-deps -e "$MPASWF_ROOT"
python -m pip install -e "$BMATRIX_ROOT"
```

On JACI, load the MPAS-JEDI environment from the B-matrix checkout:

```bash
cd "$BMATRIX_ROOT"
export STACK_ROOT=/path/to/spack-stack
source scripts/load_jaci_env.sh
```

## 1. Upstream pair generation

The NMC forecast pairs are generated before this package starts. The operational
tool used for that upstream step is `mpaswf`.

The upstream chain is:

```text
GFS GRIB2
  -> WPS/ungrib
  -> FILE:YYYY-MM-DD_HH
  -> mpas_init_atmosphere
  -> MPAS initial conditions
  -> MPAS atmosphere forecasts f024 and f048
  -> same-valid-time forecast pair
  -> forecast-pair manifest
```

For each valid time `T`, the NMC pair is:

```text
f048 initialized at T - 48 h
minus
f024 initialized at T - 24 h
```

The B-matrix package does not rerun this meteorological workflow. It consumes
the results as a manifest or as an already prepared BFLOW workspace.

Keep this separation:

```text
mpaswf
  produces MPAS states and NMC forecast pairs

mpas-bmatrix BFLOW
  transforms those pairs into FULL and PTB products

SABER/BUMP stages
  calibrate, validate and diagnose the static B-matrix
```

A generic upstream run is:

```bash
cd "$MPASWF_ROOT"
MPASWF_CONFIG=/path/to/mpaswf-config.yaml

mpaswf run --phase prepare  --config "$MPASWF_CONFIG"
mpaswf run --phase init     --config "$MPASWF_CONFIG" --submit --wait
mpaswf run --phase forecast --config "$MPASWF_CONFIG" --submit --wait
mpaswf run --phase manifest --config "$MPASWF_CONFIG"
```

The hand-off file is:

```text
/path/to/mpaswf-work/products/mpas-forecast-manifest.tsv
```

## 2. BFLOW

BFLOW is the boundary stage. It prepares MPAS/JEDI control-space perturbations
from NMC forecast pairs.

Expected products:

```text
FULL_f24.nc
FULL_f48.nc
PTB_f48mf24.nc
template_PTB.nc
manifest.tsv
ESMF_weights/weights_manifest.json
```

BFLOW uses the scientific contract in `configs/bmatrix-x1.10242.yaml`:

- `bflow.nmc` declares the NMC lead times: f048 minus f024.
- `bflow.products` declares product names.
- `bflow.regridding` owns the MPAS-to-latlon weight configuration.
- `bflow.wind_transform` declares the conversion to streamfunction and velocity
  potential.
- `bflow.derived_variables` creates analysis/control variables such as air
  temperature and specific humidity from MPAS-native fields.

Build BFLOW from the `mpaswf` manifest:

```bash
cd "$BMATRIX_ROOT"
CONFIG=configs/jaci-x1.10242.yaml
MANIFEST=/path/to/mpaswf-work/products/mpas-forecast-manifest.tsv

PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage bflow \
  --clean \
  --poll-seconds 30
```

After BFLOW exists, later runs can resume from an explicit BFLOW workspace:

```bash
BFLOW="$WORK_ROOT/bmatrix/bflow_preprocessing/np128_<START_VALID>_<END_VALID>"
```

## 3. VBAL

VBAL estimates the vertical-balance coefficients used by the `K2` transform.

Expected products:

```text
VBAL/mpas_vbal.nc
VBAL/mpas_sampling.nc
VBAL/mpas_vbal_local_*
VBAL/mpas_sampling_local_*
```

VBAL is a calibration stage. It does not, by itself, provide a reliable public
contract for writing the final unbalanced ensemble members on disk.

## 4. UNBALANCE

UNBALANCE is an explicit stage added to materialize the members needed by HDIAG.

It applies `K2^-1` to centered perturbations and writes:

```text
samplesUnbalanced/PTB_f48mf24_001.nc
samplesUnbalanced/PTB_f48mf24_002.nc
samplesUnbalanced/PTB_f48mf24_003.nc
samplesUnbalanced/PTB_f48mf24_004.nc
```

Those files are not raw PTBs. They are centered perturbations in the unbalanced
control space. HDIAG must use these files exclusively.

## 5. HDIAG

HDIAG computes global diagnostics from `samplesUnbalanced`.

Expected products:

```text
HDIAG/mpas.stddev.nc
HDIAG/mpas.cor_rh.nc
HDIAG/mpas.cor_rv.nc
```

The HDIAG sampling must keep the distance extent below the default BUMP universe
radius. For the validated case:

```yaml
distance classes: 10
distance class width: 1000000.0
```

This keeps `(10 - 1) * 1000000` below the default BUMP limit.

## 6. NICAS

NICAS builds the local/global correlation model and normalization diagnostics.

Expected products:

```text
merge/mpas_nicas.nc
merge/mpas.nicas_norm.nc
merge/mpas.dirac_nicas.nc
mpas_nicas_local_*
mpas_nicas_grids_local_*
```

For SO and DIRAC reads, `BUMP_NICAS.read.grids` must split the controls by
vertical dimensionality:

```text
3D: stream_function, velocity_potential, temperature, spechum
2D: surface_pressure
```

Without this split, BUMP can try to read the 2D `surface_pressure` local NICAS
group using a 3D `nl0`, leading to `wrong size for dimension nl0`.

## 7. SO

SO is a variational single-observation validation of the complete B composition.

It exercises:

```text
BUMP_NICAS + StdDev + BUMP_VerticalBalance + Control2Analysis
```

Expected outputs:

```text
SO/an.*.nc
SO/obsout_SO_T.h5
SO/obsout_SO_U.h5
```

`SO/an.*.nc` is MPAS-native output written by MPAS streams. It is not expected to
contain canonical JEDI variables. A successful SO is identified by:

- final OOPS status `with status = 0`;
- `CostFunction::addIncrement: Analysis` in the runlog;
- obsout files;
- an MPAS-native `an.*.nc` in CDF5 format.

## 8. DIRAC

DIRAC applies a complete-B impulse response test.

The validated contract follows the functional main workflow:

```yaml
dirac:
  ndir: 1
  dirLats: [...]
  dirLons: [...]
  ildir: 10
  dirvar: air_temperature

output dirac:
  filename: ./mpas.dirac.nc
  date: '2026-06-22T00:00:00Z'
  stream name: control
```

Do not replace this with reduced `dirLevs`/`dirVars` lists without revalidating
the MPAS-JEDI/SABER contract.

Expected product:

```text
DIRAC/mpas.dirac.nc
```

## 9. PLOTS

PLOTS is local post-processing. It does not change scientific products.

Expected products:

```text
summary.csv
README.md
01_stddev/
02_corr_horizontal/
03_corr_vertical/
04_vbal/
05_dirac/
06_spatial_fields/
```

Use plots to check that B amplitudes, correlation scales, balance diagnostics
and DIRAC responses are physically plausible.
