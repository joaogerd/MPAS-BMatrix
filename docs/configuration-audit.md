# Configuration audit: original three-file layout

This report records how the original files in `configs/` were used before the
configuration reorganization.

Audited files:

```text
configs/bmatrix-x1.10242.yaml
configs/jaci-x1.10242.yaml
configs/jaci.yaml
```

## Executive summary

The public CLI used `configs/jaci-x1.10242.yaml` by default. That file pointed to
`configs/bmatrix-x1.10242.yaml` through `bmatrix.configuration`; the loader read
both and deep-merged them. `configs/jaci.yaml` was not referenced by the CLI,
loader, scripts, tests or stage modules and used a schema incompatible with the
current BFLOW-onward pipeline.

The effective pre-change layout was therefore:

```text
ACTIVE ENTRY POINT
  configs/jaci-x1.10242.yaml
      |
      +-- bmatrix.configuration
              |
              +-- configs/bmatrix-x1.10242.yaml

LEGACY / NOT LOADED
  configs/jaci.yaml
```

Main findings:

1. `jaci-x1.10242.yaml` mixed JACI/site settings, x1.10242 case settings and
   obsolete upstream WPS/forecast settings.
2. `bmatrix-x1.10242.yaml` contained every independent scientific stage in one
   large document.
3. the UNBALANCE executable was placed in the scientific contract and used a
   user-specific absolute path;
4. `jaci.yaml` duplicated an older monolithic forecast/B-matrix design and
   contradicted the active configuration;
5. active committed paths used one developer's directory tree and retained the
   old repository name `mpas-bmatrix-global`.

## 1. How configuration was loaded

The public command declared:

```text
DEFAULT_CONFIG = configs/jaci-x1.10242.yaml
```

The following subcommands all called `load_config()`:

```text
check-config
weights
build
validate
plots
products
```

The original loader performed:

```text
1. load the platform YAML passed with --config;
2. recursively expand environment variables in values;
3. read bmatrix.configuration, when present;
4. load the scientific YAML;
5. deep-merge scientific contract <- platform configuration;
6. validate the minimum merged shape.
```

Mappings were merged recursively. Lists were atomic and replaced rather than
concatenated, protecting ordered scientific sequences such as controls,
relations and observations.

## 2. Original `configs/jaci-x1.10242.yaml`

### Actual role

This was the runnable platform/case entry point and the CLI default.

### Keys actively consumed by the current package

| Key | Main consumer | Purpose |
| --- | --- | --- |
| `project.project_root` | scheduler | Resolves the repository-local environment loader inside PBS scripts. |
| `project.work_root` | workspace models | Root of deterministic BFLOW/covariance/plot workspaces. |
| `environment.loader` | scheduler | Script sourced by generated PBS jobs. |
| `install.root` | VBAL/HDIAG/NICAS/DIRAC/SO | Installation prefix for covariance toolbox and variational executables. |
| `install.atmosphere_share` | static staging | MPAS atmosphere tables/files linked into workspaces. |
| `mesh.name` | paths/staging | MPAS mesh identifier. |
| `mesh.grid` | validation/BFLOW/ESMF | MPAS mesh NetCDF. |
| `mesh.graph` | static staging | MPAS graph file. |
| `mesh.partitions_dir` | static staging | Directory containing graph partitions. |
| `mesh.nproc` | paths/PBS/NICAS merge | MPI ranks and partition suffix. |
| `mesh.nvertlevels` | NICAS | Converts level-from-top to a model level. |
| `static.invariant` | static staging | Invariant MPAS state. |
| `static.tutorial_physics_files` | static staging | Compatible namelist, streams and stream-list source. |
| `static.geovars` | static staging | MPAS-JEDI GeoVaLs definitions. |
| `static.keptvars` | static staging | MPAS-JEDI kept-variable definitions. |
| `bmatrix.configuration` | loader | Scientific-contract path. |
| `pbs.queues.bmatrix` | scheduler | Queue for B-matrix jobs. |
| `pbs.walltime.bmatrix` | scheduler | Walltime for B-matrix jobs. |
| `runtime.config_dt` | BFLOW range discovery | MPAS time step encoded in upstream forecast paths. |

### Keys not used by the current package

These values belonged to upstream forecast production, which is now owned by
`mpaswf`, or duplicated active settings:

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

`project.name` was metadata only and still contained the old repository name.

### Problems

- site and case concerns were inseparable;
- obsolete WPS/forecast keys obscured the BFLOW boundary;
- paths were tied to one account;
- duplicated queue/rank/walltime keys could diverge;
- the file was difficult to reuse for another mesh.

## 3. Original `configs/bmatrix-x1.10242.yaml`

### Actual role

This was the scientific contract referenced by the active JACI case. Its
sections were consumed by stage-specific renderers:

| Section | Consumers |
| --- | --- |
| `controls` | all stages, aliases, stream lists and 3D/2D grouping |
| `bflow` | pair semantics, product names, regridding, wind transform, derived variables and validation |
| `vbal` | VBAL calibration and later SO/DIRAC VBAL reads |
| `unbalance` | executable resolution only |
| `hdiag` | HDIAG calibration and distance-extent validation |
| `nicas` | per-control NICAS calibration, diagnostics and merge |
| `single_observation` | SO minimization, variables, observations and variants; DIRAC also reused its analysis-variable list |
| `dirac` | complete-B impulse point, control and background variables |

### Problems

- independent pipeline stages were coupled in one long file;
- the stage rebuild boundary was not obvious;
- one machine-specific executable path was mixed with scientific parameters;
- comments documented only selected keys;
- reviewing one stage required navigating unrelated sections;
- `schema_version` was informational but not tied to a clear composition layout.

### Split feasibility

A stage split is safe and appropriate because:

- each stage already has a separate Python module and product contract;
- the configuration loader deep-merges mappings;
- lists are already atomic, so includes cannot silently concatenate controls or
  observations;
- a small aggregator can retain one public scientific-contract path;
- stage-local comments can be detailed without making one monolithic file
  unreadable.

## 4. Original `configs/jaci.yaml`

### Actual role

None. No current code path referenced the filename or its unique keys.

### Legacy/incompatible keys

```text
project.root
monan_jedi.*
mpas.*
jedi.toolbox
dates.*
physics.*
external_data.*
nmc.*
bmatrix.type
bmatrix.use_vertical_balance
```

The file also contradicted the active workflow:

```text
jaci.yaml mesh.nproc                  = 64
jaci-x1.10242.yaml mesh.nproc         = 128

jaci.yaml bmatrix.use_vertical_balance = false
current pipeline                        = explicit VBAL stage
```

Its dates, forecast leads, GFS/intermediate roots, MPAS executables and physics
suite belonged to an older combined forecast/B-matrix workflow. Those upstream
responsibilities now belong to `mpaswf`.

## 5. Audit recommendation

Repurpose the three public files with clear ownership:

```text
configs/jaci.yaml
  JACI site/runtime base

configs/jaci-x1.10242.yaml
  runnable JACI + x1.10242 case entry point

configs/bmatrix-x1.10242.yaml
  scientific-contract aggregator

configs/bmatrix/x1.10242/*.yaml
  one documented scientific fragment per stage
```

The user-facing command remains unchanged:

```bash
mpas-bmatrix build --config configs/jaci-x1.10242.yaml ...
```
