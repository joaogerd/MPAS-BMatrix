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

The public entry point remains:

```text
configs/jaci-x1.10242.yaml
```

The complete merge path is now:

```text
configs/jaci.yaml
        ↓ included by
configs/jaci-x1.10242.yaml
        ↓ references
configs/bmatrix-x1.10242.yaml
        ↓ includes
configs/bmatrix/x1.10242/*.yaml
```

## 2. Loader change

The YAML loader now supports:

```yaml
include: another-file.yaml
```

or:

```yaml
include:
  - first.yaml
  - second.yaml
```

Rules:

1. include paths are relative to the file that declares them;
2. included files are merged in declaration order;
3. the including file overrides included mappings;
4. mappings are merged recursively;
5. lists are atomic and replaced, never concatenated;
6. include cycles are rejected with an explicit error;
7. `check-config` provenance records all platform and scientific source files.

This allows the scientific contract to be split without changing the merged
mapping consumed by stage code.

## 3. Corrected responsibility of each public file

### `configs/jaci.yaml`

Now contains only JACI site/runtime/build settings:

```text
project.project_root
project.work_root
environment.loader
install.root
install.atmosphere_share
install.unbalance_executable
pbs.queues.bmatrix
pbs.walltime.bmatrix
```

The old unused monolithic schema was removed. Paths are expressed through
explicit environment variables rather than a developer's absolute directories.

### `configs/jaci-x1.10242.yaml`

Now contains only x1.10242 case settings:

```text
include: jaci.yaml
mesh.*
static.*
bmatrix.configuration
runtime.config_dt
```

WPS, GFS, MPAS initialization and forecast settings were removed because
`mpaswf` owns that upstream workflow.

### `configs/bmatrix-x1.10242.yaml`

Now acts as a short scientific-contract aggregator. It declares the layout
version and includes one file per stage in pipeline order.

The change preserves the familiar path used by `bmatrix.configuration` while
making ownership and rebuild boundaries visible.

## 4. Stage fragments

| File | Ownership | Earliest required rebuild after change |
| --- | --- | --- |
| `controls.yaml` | canonical/file names and 3D/2D dimensions | BFLOW |
| `bflow.yaml` | NMC pair semantics, products, transforms, derived variables | BFLOW |
| `vbal.yaml` | balance sampling, drivers and relations | VBAL |
| `unbalance.yaml` | explicit stage marker; currently no tunable scientific key | UNBALANCE when future keys are added |
| `hdiag.yaml` | variance/correlation sampling and fitting | HDIAG |
| `nicas.yaml` | NICAS compression and internal diagnostics | NICAS |
| `single-observation.yaml` | complete-B variational validation | SO; DIRAC when analysis variables change |
| `dirac.yaml` | complete-B impulse response | DIRAC |

PLOTS has no scientific fragment because its current options (`level`, `dpi`,
selected variables and output workspace) are run-specific CLI choices rather
than calibration parameters.

## 5. UNBALANCE correction

The old scientific file contained a user-specific executable path:

```text
unbalance.executable
```

Executable location is a platform/build concern, not a scientific parameter. It
was moved to:

```text
install.unbalance_executable
```

in `configs/jaci.yaml`.

The code now resolves the executable in this order:

1. `install.unbalance_executable`;
2. standard `install.root/bin/mpasjedi_unbalance_ensemble.x`;
3. legacy `unbalance.executable` for backward compatibility.

The hard-coded developer path was removed from Python and YAML.

## 6. Removed obsolete or duplicated settings

The active configuration no longer declares settings unused by this repository:

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

These were either upstream `mpaswf` responsibilities or duplicates of
`mesh.nproc`, `pbs.queues.bmatrix` and `pbs.walltime.bmatrix`.

## 7. Portability correction

Committed configuration now uses:

```text
BMATRIX_ROOT
WORK_ROOT
MONAN_JEDI_INSTALL
MONAN_JEDI_UNBALANCE_EXE
MPAS_MESH_ROOT
MPAS_JEDI_STATIC_ROOT
MONAN_JEDI_SOURCE
```

This removes personal paths and makes the same files usable by another INPE/MONAN
team member after exporting site-appropriate roots.

## 8. Inline documentation

Every YAML now starts with:

- purpose;
- modification rules;
- ownership boundary;
- rebuild consequences where applicable.

Every active parameter/key has an adjacent explanation. The comments distinguish:

- canonical JEDI names from NetCDF file names;
- site/build parameters from scientific parameters;
- upstream mpaswf settings from BFLOW-onward settings;
- NICAS internal diagnostics from the complete-B DIRAC stage;
- training/calibration parameters from SO validation observations.

## 9. Tests added

The test suite now covers:

```text
- recursive platform/case/scientific includes;
- deterministic include-source provenance;
- atomic list replacement;
- include-cycle rejection;
- complete composition of the repository's default x1.10242 case;
- absence of the obsolete WPS block in the resolved configuration.
```

## 10. User-visible behavior

The normal command does not change:

```bash
mpas-bmatrix check-config --config configs/jaci-x1.10242.yaml
```

The resolved output is still one mapping containing `controls`, `bflow`, `vbal`,
`unbalance`, `hdiag`, `nicas`, `single_observation` and `dirac`. Stage code does
not need to know which fragment supplied each section.
