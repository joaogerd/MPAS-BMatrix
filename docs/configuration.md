# Configuration guide

MPAS-BMatrix uses a composed YAML hierarchy so machine settings, mesh/case
settings and stage-specific scientific parameters can be reviewed independently.

## 1. Public entry point and file hierarchy

```text
configs/jaci.yaml
  JACI site/build base; included, not normally passed directly to the CLI

configs/jaci-x1.10242.yaml
  runnable x1.10242 case; includes jaci.yaml

configs/bmatrix-x1.10242.yaml
  scientific-contract aggregator referenced by the case

configs/bmatrix/x1.10242/*.yaml
  controls plus one scientific fragment per BFLOW-through-DIRAC stage
```

Users normally pass only:

```bash
mpas-bmatrix check-config --config configs/jaci-x1.10242.yaml
```

## 2. Required environment variables

Export these paths before checking or running the x1.10242 case:

```bash
export BMATRIX_ROOT=/path/to/projects/MPAS-BMatrix
export WORK_ROOT=/path/to/work/MPAS-BMatrix

export MONAN_JEDI_SOURCE=/path/to/projects/MONAN-JEDI
export MONAN_JEDI_INSTALL=/path/to/install/monan-jedi-mpas
export MONAN_JEDI_UNBALANCE_EXE=/path/to/mpasjedi_unbalance_ensemble.x

export MPAS_MESH_ROOT=/path/to/mpas_meshes
export MPAS_JEDI_STATIC_ROOT=/path/to/validated/x1.10242/static-files

export STACK_ROOT=/path/to/spack-stack
```

`MPAS_JEDI_STATIC_ROOT` must contain at least:

```text
x1.10242.invariant.nc
namelist.atmosphere_240km
streams.atmosphere_240km
stream_list.atmosphere.*
```

The namelist, streams and stream lists must match the installed MPAS Registry
and physics tables.

Load the runtime and inspect the resolved configuration:

```bash
cd "$BMATRIX_ROOT"
source scripts/load_jaci_env.sh
mpas-bmatrix check-config --config configs/jaci-x1.10242.yaml
```

The JSON output includes:

```text
configuration_sources
bmatrix_contract_path
bmatrix_contract_sources
```

A missing environment variable causes `check-config` to fail before any PBS job
is generated and reports the unresolved YAML key.

## 3. Include semantics

A YAML may include one file:

```yaml
include: jaci.yaml
```

or several files:

```yaml
include:
  - controls.yaml
  - bflow.yaml
  - vbal.yaml
```

Rules:

1. paths are relative to the declaring YAML;
2. files are merged in listed order;
3. the declaring file overrides included mappings;
4. nested mappings are merged recursively;
5. lists are replaced as complete units;
6. cyclic includes are rejected;
7. unresolved environment-variable references are rejected.

Example:

```yaml
# base.yaml
pbs:
  queues:
    bmatrix: pesqmidi
  walltime:
    bmatrix: "02:00:00"
```

```yaml
# local-case.yaml
include: base.yaml
pbs:
  walltime:
    bmatrix: "04:00:00"
```

Resolved result:

```yaml
pbs:
  queues:
    bmatrix: pesqmidi
  walltime:
    bmatrix: "04:00:00"
```

## 4. Where to change a value

| Change | File |
| --- | --- |
| JACI queue, walltime, install roots or environment loader | `configs/jaci.yaml` or its referenced environment variables |
| MPAS mesh path, partition count, vertical levels or static files | `configs/jaci-x1.10242.yaml` |
| Control-variable names/aliases and 3D/2D grouping | `configs/bmatrix/x1.10242/controls.yaml` |
| NMC/BFLOW preprocessing | `configs/bmatrix/x1.10242/bflow.yaml` |
| Vertical-balance calibration/inverse settings | `configs/bmatrix/x1.10242/vbal.yaml` |
| K2^-1 BUMP read flags | `configs/bmatrix/x1.10242/unbalance.yaml` |
| HDIAG statistics | `configs/bmatrix/x1.10242/hdiag.yaml` |
| NICAS | `configs/bmatrix/x1.10242/nicas.yaml` |
| Single-observation validation | `configs/bmatrix/x1.10242/so.yaml` |
| Complete-B DIRAC control and paired points | `configs/bmatrix/x1.10242/dirac.yaml` |

## 5. Stage-specific clarity rules

### Control names

`controls.yaml` distinguishes:

```text
code        canonical name used internally by JEDI/SABER/OOPS
file        physical name written in B-matrix NetCDF products
dimensions  3d or 2d, used by NICAS grid grouping
```

These aliases do not make canonical names valid MPAS stream fields. MPAS stream
lists continue to use Registry-native names.

### UNBALANCE

The executable is infrastructure:

```text
install.unbalance_executable
```

The scientific fragment contains only the BUMP read contract used to apply the
calibrated balance:

```text
read local sampling
read global sampling
read vertical balance
```

### DIRAC

Candidate coordinates are stored as paired mappings:

```yaml
points:
  - {latitude: 30.31011691, longitude: 130.11182691}
  - {latitude: -34.60250161, longitude: -58.39753137}
```

`index` is one-based and selects one mapping. The renderer converts this form to
`dirLats`, `dirLons`, `ildir` and `dirvar` for the toolbox. Older contracts with
parallel `latitudes`/`longitudes` remain readable, but new profiles should use
`points`.

## 6. Rebuild rules

A configuration change invalidates that stage and all downstream stages:

```text
controls or BFLOW
  -> BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS

VBAL
  -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS

UNBALANCE
  -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS

HDIAG
  -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS

NICAS
  -> NICAS -> SO -> DIRAC -> PLOTS

SO observation/minimizer
  -> SO

SO analysis variables
  -> SO -> DIRAC -> PLOTS

DIRAC point/control/background list
  -> DIRAC -> PLOTS
```

Run from the earliest invalid stage with `--clean`.

## 7. Adding another mesh/case

For a new mesh, create:

```text
configs/jaci-<mesh>.yaml
configs/bmatrix-<mesh>.yaml
configs/bmatrix/<mesh>/
```

Recommended procedure:

1. copy `jaci-x1.10242.yaml` and replace mesh/static/runtime settings;
2. reuse scientific fragments only after verifying the same assumptions;
3. otherwise copy the x1.10242 fragment directory and review every stage;
4. point `bmatrix.configuration` to the new aggregator;
5. add a configuration-composition test;
6. run `check-config`, unit tests and a JACI smoke test.

Do not reuse x1.10242 sampling sizes, vertical levels, partitions or static files
without checking compatibility with the new mesh.

## 8. Local overrides

Avoid editing committed YAML only to change personal roots; use the documented
environment variables. For an intentional experiment, create a case file that
includes the official case and overrides only the required mapping:

```yaml
# configs/jaci-x1.10242-experiment.yaml
include: jaci-x1.10242.yaml

pbs:
  walltime:
    bmatrix: "04:00:00"
```

Because lists are atomic, overriding `controls`, `relations`, `points` or
`background_variables` requires repeating the complete intended list.

## 9. Audit and implementation reports

- [`configuration-audit.md`](configuration-audit.md): how the original three
  files were actually used and which keys were obsolete.
- [`configuration-reorganization.md`](configuration-reorganization.md): final
  ownership, corrections, compatibility behavior and tests.
