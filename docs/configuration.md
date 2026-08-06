# Configuration guide

MPAS-BMatrix uses a composed YAML hierarchy so machine settings, mesh/case
settings and stage-specific scientific parameters can be reviewed independently.

## 1. File hierarchy

```text
configs/jaci.yaml
  JACI site/build/runtime base

configs/jaci-x1.10242.yaml
  runnable x1.10242 case; includes jaci.yaml

configs/bmatrix-x1.10242.yaml
  scientific-contract aggregator referenced by the case

configs/bmatrix/x1.10242/*.yaml
  one scientific fragment per pipeline stage
```

Users should normally pass only the runnable case:

```bash
mpas-bmatrix check-config --config configs/jaci-x1.10242.yaml
```

## 2. Required environment variables

Export these paths before loading/checking/running the x1.10242 case:

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

The static namelist/streams/stream lists must be compatible with the installed
MPAS Registry and physics tables.

Load the runtime and inspect the composed result:

```bash
cd "$BMATRIX_ROOT"
source scripts/load_jaci_env.sh
mpas-bmatrix check-config --config configs/jaci-x1.10242.yaml
```

The resolved JSON includes:

```text
configuration_sources
bmatrix_contract_path
bmatrix_contract_sources
```

These fields show exactly which YAML documents formed the run configuration.
A missing environment variable causes `check-config` to fail and reports the
YAML key that still contains the unresolved reference.

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
| JACI queue or walltime | `configs/jaci.yaml` |
| MONAN-JEDI installation or UNBALANCE executable | environment variables referenced by `configs/jaci.yaml` |
| MPAS mesh path, partition count or vertical levels | `configs/jaci-x1.10242.yaml` |
| Static namelist/streams/invariant roots | environment variables referenced by `configs/jaci-x1.10242.yaml` |
| Control-variable set | `configs/bmatrix/x1.10242/controls.yaml` |
| NMC/BFLOW preprocessing | `configs/bmatrix/x1.10242/bflow.yaml` |
| Vertical balance | `configs/bmatrix/x1.10242/vbal.yaml` |
| HDIAG statistics | `configs/bmatrix/x1.10242/hdiag.yaml` |
| NICAS | `configs/bmatrix/x1.10242/nicas.yaml` |
| Single-observation validation | `configs/bmatrix/x1.10242/so.yaml` |
| Complete-B DIRAC | `configs/bmatrix/x1.10242/dirac.yaml` |

## 5. Rebuild rules

A configuration change invalidates that stage and all downstream stages.

```text
controls/BFLOW change
  -> BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS

VBAL change
  -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS

HDIAG change
  -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS

NICAS change
  -> NICAS -> SO -> DIRAC -> PLOTS

SO observation/minimizer change
  -> SO only

SO analysis-variable change
  -> SO and DIRAC

DIRAC point/variable change
  -> DIRAC -> PLOTS
```

Run the pipeline from the earliest invalid stage with `--clean`.

## 6. Adding another mesh/case

For a new mesh, create:

```text
configs/jaci-<mesh>.yaml
configs/bmatrix-<mesh>.yaml
configs/bmatrix/<mesh>/
```

Recommended procedure:

1. copy `jaci-x1.10242.yaml` and replace only mesh/static/runtime settings;
2. start by reusing the scientific fragments only if the same scientific
   assumptions are valid;
3. otherwise copy the x1.10242 fragment directory and review every stage;
4. point the new case's `bmatrix.configuration` to its aggregator;
5. add a configuration-composition test;
6. run `check-config`, unit tests and a JACI smoke test.

Do not reuse x1.10242 sampling sizes, vertical levels, partitions or static files
without checking their compatibility with the new mesh.

## 7. Local overrides

Avoid editing committed YAML only to change personal roots; use the documented
environment variables. For an intentional experimental override, create a case
file in `configs/` that includes the official case and changes only the required
mapping:

```yaml
# configs/jaci-x1.10242-experiment.yaml
include: jaci-x1.10242.yaml

pbs:
  walltime:
    bmatrix: "04:00:00"
```

Because lists are atomic, overriding a list such as `controls`, `relations` or
`background_variables` requires repeating the complete intended list.
