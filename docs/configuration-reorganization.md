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
        ├── single-observation.yaml
        └── dirac.yaml
```

The public configuration entry point remains:

```text
configs/jaci-x1.10242.yaml
```

The composition path is:

```text
configs/jaci.yaml
        ↓ included by
configs/jaci-x1.10242.yaml
        ↓ references
configs/bmatrix-x1.10242.yaml
        ↓ includes
configs/bmatrix/x1.10242/*.yaml
```

## 2. Loader changes

The YAML loader now accepts one include:

```yaml
include: another-file.yaml
```

or an ordered include list:

```yaml
include:
  - first.yaml
  - second.yaml
```

Composition rules:

1. paths are resolved relative to the file declaring the include;
2. included files are merged in declaration order;
3. the including file overrides included mappings;
4. nested mappings are deep-merged;
5. lists are atomic and replaced rather than concatenated;
6. include cycles are rejected;
7. unresolved environment variables are rejected before stage execution;
8. resolved configuration provenance records every platform and scientific YAML
   source.

This preserves one final mapping for stage code while allowing clear file
ownership.

## 3. Final responsibility of each public file

### `configs/jaci.yaml`

Owns only JACI site/runtime/build settings:

```text
project.name
project.project_root
project.work_root
environment.loader
install.root
install.atmosphere_share
install.unbalance_executable
pbs.queues.bmatrix
pbs.walltime.bmatrix
```

The file uses environment variables instead of committed user-specific paths.
It contains no scientific calibration values and no upstream forecast settings.

### `configs/jaci-x1.10242.yaml`

Owns only the runnable x1.10242 case:

```text
include: jaci.yaml
mesh.*
static.*
bmatrix.configuration
runtime.config_dt
```

WPS, GFS, MPAS initialization and forecast settings were removed because those
belong to `mpaswf`.

### `configs/bmatrix-x1.10242.yaml`

Is now a short scientific-contract aggregator. It declares `schema_version: 2`
and includes one documented fragment per scientific stage in workflow order.

The familiar `bmatrix.configuration` path remains unchanged, so users still pass
only `configs/jaci-x1.10242.yaml` to the CLI.

## 4. Scientific stage fragments

| File | Ownership | Earliest rebuild after change |
| --- | --- | --- |
| `controls.yaml` | canonical/file control names and 3D/2D dimensions | BFLOW |
| `bflow.yaml` | NMC leads, product interfaces, regridding, wind transform, derived variables and checks | BFLOW |
| `vbal.yaml` | VBAL variable order, drivers, sampling and balance relations | VBAL |
| `unbalance.yaml` | explicit stage marker; no current tunable scientific value | future key-dependent |
| `hdiag.yaml` | ensemble threshold, variance/correlation sampling and fitting | HDIAG |
| `nicas.yaml` | NICAS compression, drivers and internal diagnostic points | NICAS |
| `single-observation.yaml` | complete-B variational validation and synthetic observations | SO; also DIRAC when analysis variables change |
| `dirac.yaml` | complete-B impulse point, control and background variables | DIRAC |

PLOTS remains configured by run-specific CLI options (`--plot-level`,
`--plot-dpi`, variable selection and optional output workspace), so no persistent
scientific fragment was added.

## 5. UNBALANCE correction

The original scientific contract contained a user-specific executable path:

```text
unbalance.executable
```

Executable location is a platform/build concern. It now belongs to:

```text
install.unbalance_executable
```

in `configs/jaci.yaml`.

Resolution order is:

1. explicit `install.unbalance_executable`;
2. legacy explicit `unbalance.executable` for backward compatibility;
3. conventional `install.root/bin/mpasjedi_unbalance_ensemble.x`.

This order avoids silently replacing a valid legacy separate build merely because
`install.root` is present.

The previous hard-coded developer path was removed from Python and YAML.

## 6. Removed obsolete or duplicated settings

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

These were either upstream `mpaswf` responsibilities or duplicates of active
settings such as `mesh.nproc`, `pbs.queues.bmatrix` and
`pbs.walltime.bmatrix`.

The old unused `jaci.yaml` schema (`dates`, `external_data`, `physics`, `nmc`,
`mpas`, `jedi`, and `bmatrix.use_vertical_balance`) was removed completely.

## 7. Portability correction

The default x1.10242 case now uses these environment variables:

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

`STACK_ROOT` is consumed by `scripts/load_jaci_env.sh`; the remaining variables
are expanded by the YAML loader.

A missing variable now raises an explicit `ConfigurationError` that reports the
YAML key path and variable name. This prevents PBS jobs from being generated with
literal `${VARIABLE}` paths.

## 8. Inline YAML documentation

Every public and stage YAML now documents:

- its purpose;
- what belongs and does not belong in the file;
- how it is composed;
- how users should modify it;
- rebuild consequences;
- every active key/parameter immediately next to the value.

The comments distinguish:

- canonical JEDI names from physical NetCDF names;
- site/build values from scientific values;
- upstream `mpaswf` settings from BFLOW-onward settings;
- NICAS internal diagnostics from complete-B DIRAC;
- calibration parameters from SO synthetic validation observations;
- 3D controls from the 2D surface-pressure control.

## 9. Provenance added to resolved configuration

`mpas-bmatrix check-config` now reports:

```text
configuration_sources
bmatrix_contract_path
bmatrix_contract_sources
```

This records exactly which site, case, aggregator and stage-fragment YAML files
formed a run.

## 10. Tests added or extended

The test suite covers:

```text
recursive site/case/scientific includes
include ordering and source provenance
atomic list replacement
include-cycle rejection
unresolved environment-variable rejection
complete composition of the repository x1.10242 case
absence of the obsolete WPS block
UNBALANCE executable precedence and backward compatibility
```

## 11. User-visible behavior

The normal public commands remain unchanged:

```bash
mpas-bmatrix check-config --config configs/jaci-x1.10242.yaml

mpas-bmatrix build \
  --config configs/jaci-x1.10242.yaml \
  --manifest /path/to/mpas-forecast-manifest.tsv
```

The fully resolved mapping still contains the same scientific top-level sections
expected by stage code:

```text
controls
bflow
vbal
unbalance
hdiag
nicas
single_observation
dirac
```

The difference is organizational: users now edit the file that owns the stage or
platform concern instead of navigating one monolithic contract.
