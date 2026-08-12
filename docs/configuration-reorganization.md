# Configuration reorganization report

This report describes the configuration corrections implemented after the audit
in [`configuration-audit.md`](configuration-audit.md).

## 1. Final layout

```text
configs/
├── jaci.yaml
├── jaci-x1.10242.yaml
├── bmatrix-x1.10242.yaml
└── bmatrix/
    └── x1.10242/
        ├── controls.yaml
        ├── bflow.yaml
        ├── vbal.yaml
        ├── unbalance.yaml
        ├── hdiag.yaml
        ├── nicas.yaml
        ├── so.yaml
        └── dirac.yaml
```

The public entry point remains:

```text
configs/jaci-x1.10242.yaml
```

Composition is explicit:

```text
configs/jaci.yaml
        ↓ include
configs/jaci-x1.10242.yaml
        ↓ bmatrix.configuration
configs/bmatrix-x1.10242.yaml
        ↓ ordered includes
configs/bmatrix/x1.10242/*.yaml
```

## 2. Loader changes

Any YAML may now contain one include:

```yaml
include: another-file.yaml
```

or an ordered list:

```yaml
include:
  - first.yaml
  - second.yaml
```

Rules implemented in `src/bmatrix/config.py`:

1. include paths are resolved relative to the declaring file;
2. included files are merged in declaration order;
3. the declaring file has final precedence;
4. nested mappings are deep-merged;
5. lists are atomic and replaced, never concatenated implicitly;
6. include cycles are rejected;
7. unresolved environment variables are rejected before stage execution;
8. source provenance records every platform and scientific YAML used.

This preserves one final mapping for stage code while allowing clear ownership.

## 3. Final responsibility of the three public files

### `configs/jaci.yaml`

JACI site/build configuration shared by case files:

```text
project.*
environment.loader
environment.variables
install.*
pbs.queues.bmatrix
pbs.walltime.bmatrix
```

It contains no BUMP calibration values and no upstream GFS/WPS/forecast options.
It is an include base, not the normal CLI entry point.

`environment.variables` lists variables that must be exported explicitly inside
a PBS script before `environment.loader` is sourced. The maintained JACI case
currently declares `STACK_ROOT` there.

### `configs/jaci-x1.10242.yaml`

Runnable x1.10242 case:

```text
include: jaci.yaml
mesh.*
static.*
bmatrix.configuration
runtime.config_dt
```

WPS, GFS, MPAS initialization and forecast settings were removed because those
belong to the external `mpaswf` workflow.

### `configs/bmatrix-x1.10242.yaml`

Short scientific-contract aggregator. It declares `schema_version: 2` and
includes one documented fragment per BFLOW-through-DIRAC stage.

The normal command remains unchanged:

```bash
mpas-bmatrix build --config configs/jaci-x1.10242.yaml ...
```

## 4. Scientific fragments and rebuild boundaries

| File | Ownership | Earliest rebuild after change |
| --- | --- | --- |
| `controls.yaml` | canonical/file names and 3D/2D dimensions | BFLOW |
| `bflow.yaml` | NMC leads, products, regridding, wind transform, derived variables and validation | BFLOW |
| `vbal.yaml` | variable order, BUMP drivers, sampling, balance relations and inverse settings | VBAL |
| `unbalance.yaml` | BUMP read contract used while applying K2^-1 | UNBALANCE |
| `hdiag.yaml` | variance/correlation sampling and fitting | HDIAG |
| `nicas.yaml` | NICAS compression, drivers and internal diagnostic points | NICAS |
| `so.yaml` | complete-B variational validation and synthetic observations | SO; DIRAC too if analysis variables change |
| `dirac.yaml` | complete-B impulse control, paired candidate points and background variables | DIRAC |

PLOTS stays run-specific through CLI options such as `--plot-level` and
`--plot-dpi`, so it has no persistent scientific fragment.

## 5. UNBALANCE corrections

The original scientific contract mixed a user-specific executable path with
scientific settings. Executable location now belongs to the platform layer:

```text
install.unbalance_executable
```

Resolution order is:

1. `install.unbalance_executable`;
2. legacy `unbalance.executable` for backward compatibility;
3. `install.root/bin/mpasjedi_unbalance_ensemble.x`.

The scientific fragment now exposes only the three BUMP read flags actually used
when applying the calibrated vertical balance:

```text
read local sampling
read global sampling
read vertical balance
```

Defaults preserve the validated run. The renderer also retains defaults for old
contracts that do not yet contain `unbalance.drivers`.

## 6. DIRAC configuration correction

The old contract stored latitude and longitude in separate parallel lists. That
format is valid for the generated toolbox YAML but fragile for users: inserting
or removing one value from only one list silently misaligns every later point.

The maintained scientific fragment now uses paired mappings:

```yaml
points:
  - {latitude: 30.31011691, longitude: 130.11182691}
  - {latitude: -34.60250161, longitude: -58.39753137}
```

The renderer converts these mappings to the validated toolbox fields
`dirLats`, `dirLons`, `ildir` and `dirvar`. Legacy parallel `latitudes` and
`longitudes` remain accepted for backward compatibility.

## 7. Removed obsolete or duplicated settings

The active MPAS-BMatrix configuration no longer declares:

```text
project.data_root
install.mpas_init
install.mpas_atmosphere
install.init_share
wps.*
pbs.queue
pbs.queues.forecast
pbs.nproc
pbs.walltime.init
pbs.walltime.forecast
pbs.walltime_short
pbs.walltime_long
runtime.output_interval
```

These were upstream `mpaswf` responsibilities or duplicates of active values
such as `mesh.nproc`, `pbs.queues.bmatrix` and `pbs.walltime.bmatrix`.

The old unused `jaci.yaml` schema (`dates`, `external_data`, `physics`, `nmc`,
`mpas`, `jedi`, and `bmatrix.use_vertical_balance`) was removed.

## 8. Portability and environment validation

Committed personal paths were replaced by explicit environment variables:

```text
BMATRIX_ROOT
WORK_ROOT
MONAN_JEDI_SOURCE
MONAN_JEDI_INSTALL
MONAN_JEDI_UNBALANCE_EXE
MPAS_MESH_ROOT
MPAS_JEDI_STATIC_ROOT
STACK_ROOT
```

Missing variables raise `ConfigurationError` with the YAML key path and variable
name, preventing PBS generation with literal `${VARIABLE}` paths.

The JACI base also records `STACK_ROOT` under `environment.variables` so it can be
rendered into each PBS script before the environment loader is sourced.

## 9. PBS environment propagation found by smoke testing

The first real VBAL smoke submission exposed an HPC-specific boundary that unit
tests alone could not exercise. `qsub` accepted the job, but it disappeared
before the application command created `stdout.log`, `stderr.log` or
`run_vbal.runlog`.

The generated PBS script sourced `scripts/load_jaci_env.sh` before redirecting the
application command. That loader requires `STACK_ROOT`, while the submit helper
did not use `qsub -V`. PBS therefore could not be assumed to inherit the custom
login-shell export.

The scheduler now renders required loader variables explicitly before `source`:

```bash
export STACK_ROOT=/resolved/path/to/spack-stack
source /resolved/path/to/MPAS-BMatrix/scripts/load_jaci_env.sh
```

This is preferred to `qsub -V`: only the required variables are propagated and
the generated script remains a clear provenance artifact.

## 10. Inline documentation

Every public and stage YAML now explains:

- purpose and ownership;
- what belongs and does not belong in that file;
- how it is composed;
- how each key should be modified;
- downstream rebuild consequences;
- canonical JEDI names versus physical NetCDF names;
- calibration parameters versus validation-only settings.

## 11. Provenance

`mpas-bmatrix check-config` now reports:

```text
configuration_sources
bmatrix_contract_path
bmatrix_contract_sources
```

These fields record the site base, case, scientific aggregator and every stage
fragment forming a run.

## 12. Tests

The configuration and scheduler tests cover:

```text
recursive includes
include ordering and source provenance
atomic list replacement
cycle rejection
unresolved environment-variable rejection
complete x1.10242 composition
absence of obsolete WPS configuration
UNBALANCE executable precedence
UNBALANCE driver defaults/overrides
paired DIRAC points and legacy-list compatibility
PBS loader-variable export before the environment loader
shell quoting of propagated PBS variables
```

No full scientific job is run by these unit tests. A JACI smoke test remains
required before merging changes that alter generated stage YAML or scheduler
bootstrap behavior.
