# Configuration guide

MPAS-BMatrix separates user choices, machine/site resolution, logical resources
and the scientific workflow configuration. This avoids making personal absolute
paths part of the scientific contract.

For a normal user, the YAML hierarchy is not the first interface. Start with:

```bash
mpas-bmatrix setup --site jaci
mpas-bmatrix paths
mpas-bmatrix doctor
mpas-bmatrix check-config
```

See [`resolution-model.md`](resolution-model.md) for the detailed resolution
model.

## 1. Configuration and resolution layers

The current x1.10242 flow is:

```text
~/.config/mpas-bmatrix/setup.yaml
  semantic user choices + optional explicit private overrides

configs/sites/jaci.yaml
  site policy and physical-path resolution rules

configs/resources/x1.10242.yaml
  logical x1.10242 resource contract

        ↓ resolved roots are injected before YAML composition

configs/jaci.yaml
  JACI runtime/PBS base

configs/jaci-x1.10242.yaml
  runnable mesh/static case

configs/bmatrix-x1.10242.yaml
  scientific-contract aggregator

configs/bmatrix/x1.10242/*.yaml
  controls plus one scientific fragment per BFLOW-through-DIRAC stage
```

The site profile answers **where infrastructure can be resolved**. The resource
catalog answers **what the selected resource must contain**. The lower YAML
hierarchy remains the runtime/scientific configuration consumed by the pipeline.

## 2. Standard user setup

On JACI:

```bash
mpas-bmatrix setup --site jaci
```

The standard saved setup is intentionally small:

```yaml
site: jaci
workspace: /p/projetos/monan_das/<USER>/work/MPAS-BMatrix
resource: x1.10242
```

A user with a different work area can set only the workspace:

```bash
mpas-bmatrix setup --site jaci --workspace /path/to/work
```

A user with a private/non-standard runtime provides only the roots that differ,
for example:

```bash
mpas-bmatrix setup --site jaci \
  --monan-jedi-install /custom/monan-jedi \
  --mesh-root /custom/mpas_meshes
```

These explicit choices are persisted under `overrides:` rather than being added
as new user-specific heuristics to the site profile.

## 3. Resolution precedence

Runtime roots use this precedence:

```text
explicit environment override
        ↓
saved user override
        ↓
canonical path declared by the site profile, when one exists
        ↓
command probe from the active environment
        ↓
compatibility fallback declared by the site profile
        ↓
unresolved
```

Workspace resolution uses:

```text
explicit setup/workspace argument
        ↓
WORK_ROOT environment override
        ↓
saved user workspace
        ↓
site-profile workspace default
```

The resolver never recursively scans arbitrary user project trees.

`mpas-bmatrix paths` reports the source of every resolved root. Current source
labels are:

```text
package
argument
environment
user-config
site-profile
command-probe
compatibility-fallback
unresolved
```

`compatibility-fallback` is important: it means the path works for the current
deployment but is **not** being claimed as the canonical shared site contract.

## 4. Site profiles

Site profiles live under:

```text
configs/sites/
```

Current profiles are:

```text
configs/sites/jaci.yaml
configs/sites/generic.yaml
```

The JACI profile defines:

- default workspace;
- default logical resource;
- optional command probes;
- optional canonical site paths when they exist;
- transitional compatibility candidates/globs.

The generic profile intentionally assumes no machine-specific runtime roots.
Users on an unknown machine must provide unresolved resources explicitly rather
than letting the application guess.

## 5. Resource catalogs

Logical resource catalogs live under:

```text
configs/resources/
```

The current case uses:

```text
configs/resources/x1.10242.yaml
```

The catalog records the logical contract for x1.10242, including:

```text
resource name
nCells metadata
nVertLevels
mesh grid/graph/partition layout
required static files
transitional geovars/keptvars locations
required MPAS-JEDI executables
MPAS core_atmosphere runtime files
```

It deliberately does not contain João's, Maria's or another user's absolute
filesystem roots.

## 6. The resources behind the resolved paths

### MPAS-BMatrix repository

Resolved key:

```text
project.project_root
```

This is the checked-out/installed MPAS-BMatrix code containing configuration,
templates and the JACI environment loader. The public CLI normally derives it
from the package location; `BMATRIX_ROOT` is an advanced override only.

### User workspace

Resolved key:

```text
project.work_root
```

The default JACI location is:

```text
/p/projetos/monan_das/<USER>/work/MPAS-BMatrix
```

The deterministic layout is:

```text
<WORK_ROOT>/
└── bmatrix/
    ├── bflow_preprocessing/
    │   └── np<NPROC>_<START>_<END>/
    ├── covariance/
    │   ├── vbal/
    │   ├── unbalance/
    │   ├── hdiag/
    │   ├── nicas/
    │   ├── so/
    │   └── dirac/
    └── plots/
```

`setup` creates only the stable parent directories. Run-specific directories are
created when the workflow knows the date range and MPI size.

### MONAN-JEDI / MPAS-JEDI installation

Resolved keys:

```text
install.root
install.atmosphere_share
install.unbalance_executable
```

A compatible installation is expected to provide at least:

```text
<install>/bin/mpasjedi_error_covariance_toolbox.x
<install>/bin/mpasjedi_variational.x
<install>/bin/mpasjedi_unbalance_ensemble.x
<install>/share/MPAS/core_atmosphere/
```

The standard UNBALANCE executable is derived as:

```text
<install.root>/bin/mpasjedi_unbalance_ensemble.x
```

A separate `MONAN_JEDI_UNBALANCE_EXE` variable is no longer required by the
standard path.

### MPAS mesh

Resolved keys:

```text
mesh.grid
mesh.graph
mesh.partitions_dir
mesh.nproc
mesh.nvertlevels
```

For x1.10242 the current physical layout is equivalent to:

```text
MPAS_MESH_ROOT/
└── quasi_uniform/
    └── x1.10242_240km/
        ├── mesh/x1.10242.grid.nc
        ├── graph/x1.10242.graph.info
        └── partitions/x1.10242.graph.info.part.128
```

The `doctor` derives the required partition filename from `mesh.graph` and the
configured `mesh.nproc`.

### Static x1.10242 inputs

Resolved keys:

```text
static.invariant
static.tutorial_physics_files
static.geovars
static.keptvars
```

The resource catalog currently declares these static files:

```text
x1.10242.invariant.nc
namelist.atmosphere_240km
streams.atmosphere_240km
stream_list.atmosphere.analysis
stream_list.atmosphere.background
stream_list.atmosphere.ensemble
```

`geovars.yaml` and `keptvars.yaml` are still obtained from the MONAN-JEDI source
checkout:

```text
mpas-jedi/test/testinput/namelists/geovars.yaml
mpas-jedi/test/testinput/namelists/keptvars.yaml
```

This source-tree dependency is transitional and should disappear once these
validated resources are incorporated into a shared/versioned resource bundle.

### MPAS atmosphere share

The resource catalog also declares the MPAS runtime tables expected below:

```text
<MONAN_JEDI_INSTALL>/share/MPAS/core_atmosphere/
```

including:

```text
CAM_ABS_DATA.DBL
CAM_AEROPT_DATA.DBL
GENPARM.TBL
LANDUSE.TBL
OZONE_DAT.TBL
RRTMG_LW_DATA
RRTMG_LW_DATA.DBL
RRTMG_SW_DATA
RRTMG_SW_DATA.DBL
SOILPARM.TBL
VEGPARM.TBL
VERSION
```

### spack-stack

Resolved through:

```text
environment.variables.STACK_ROOT
```

This is site/runtime infrastructure used by generated PBS jobs to load the JACI
MPAS-JEDI environment. It is not a scientific parameter.

## 7. Advanced overrides

The recommended persistent interface for a non-standard layout is `setup`:

```bash
mpas-bmatrix setup --site jaci \
  --monan-jedi-install /path/to/install \
  --mesh-root /path/to/meshes \
  --static-root /path/to/static \
  --monan-jedi-source /path/to/MONAN-JEDI \
  --stack-root /path/to/spack-stack
```

Equivalent environment variables remain supported for one-off/developer use:

| Variable | Represents |
| --- | --- |
| `WORK_ROOT` | user workspace root |
| `MONAN_JEDI_INSTALL` | installed MPAS-JEDI/SABER prefix |
| `MPAS_MESH_ROOT` | physical MPAS mesh collection root |
| `MPAS_JEDI_STATIC_ROOT` | physical static-resource root |
| `MONAN_JEDI_SOURCE` | transitional MONAN-JEDI source checkout |
| `STACK_ROOT` | spack-stack root |
| `BMATRIX_ROOT` | MPAS-BMatrix checkout; rarely needed |

After changing any physical root, run:

```bash
mpas-bmatrix paths
mpas-bmatrix doctor
```

The application does not accept a path merely because it was configured;
`doctor` checks the concrete prerequisites at the resolved locations.

## 8. What `doctor` validates

`doctor` consumes the selected site/resource and the composed config. It checks
both the logical contract and concrete filesystem/runtime prerequisites.

Current logical checks include:

```text
selected resource mesh name == configured mesh.name
catalog nVertLevels == configured mesh.nvertlevels
```

Current filesystem/runtime checks include:

```text
repository/workspace roots
MONAN-JEDI install and atmosphere share
required executable files + execute permission
mesh grid and graph
partitions directory and np<NPROC> partition file
invariant/static root
geovars.yaml and keptvars.yaml
resource-catalog static files
resource-catalog MPAS atmosphere files
spack-stack root
```

A final:

```text
READY
```

means the resolved **preflight prerequisites** are present. It does not replace a
real PBS launch or the complete end-to-end smoke.

## 9. `check-config` versus `doctor`

`check-config` validates composition of the YAML/scientific contract. It does not
claim runtime readiness.

Human output ends with:

```text
Configuration status: VALID
Runtime readiness: NOT CHECKED by this command; run 'mpas-bmatrix doctor'.
```

Use:

```bash
mpas-bmatrix check-config --json
```

for the full composed mapping.

## 10. Values needed inside PBS jobs

Do not assume arbitrary login-shell variables are inherited by compute jobs.
Values required before the JACI environment loader runs belong under
`environment.variables` in `configs/jaci.yaml`.

Example:

```yaml
environment:
  loader: scripts/load_jaci_env.sh
  variables:
    STACK_ROOT: ${STACK_ROOT}
```

The scheduler writes the resolved value into the generated PBS script before
sourcing the loader. This avoids relying on `qsub -V` and keeps the bootstrap
auditable.

## 11. Include semantics

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

## 12. Where to change a value

| Change | File/interface |
| --- | --- |
| Normal user site/workspace/resource | `mpas-bmatrix setup` |
| Private/non-standard physical root | `mpas-bmatrix setup --<root> ...` |
| Machine resolution policy | `configs/sites/<site>.yaml` |
| Logical mesh/resource prerequisites | `configs/resources/<resource>.yaml` |
| JACI PBS queue/walltime/environment loader | `configs/jaci.yaml` |
| Runnable mesh case, ranks and vertical levels | `configs/jaci-x1.10242.yaml` |
| Control names/aliases and 3D/2D grouping | `configs/bmatrix/x1.10242/controls.yaml` |
| NMC/BFLOW preprocessing | `configs/bmatrix/x1.10242/bflow.yaml` |
| Vertical-balance calibration/inverse | `configs/bmatrix/x1.10242/vbal.yaml` |
| K2^-1 UNBALANCE scientific read flags | `configs/bmatrix/x1.10242/unbalance.yaml` |
| HDIAG statistics | `configs/bmatrix/x1.10242/hdiag.yaml` |
| NICAS | `configs/bmatrix/x1.10242/nicas.yaml` |
| Single-observation validation | `configs/bmatrix/x1.10242/so.yaml` |
| Complete-B DIRAC control/points | `configs/bmatrix/x1.10242/dirac.yaml` |

## 13. Stage-specific clarity rules

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

The stage scientific fragment contains the BUMP read contract used to apply the
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

`index` is one-based and selects one mapping. The renderer converts it to the
keys required by the toolbox.

## 14. Rebuild rules

A scientific configuration change invalidates that stage and all downstream
stages:

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

A site/root change is different: first rerun `paths` and `doctor`, then regenerate
from the earliest stage whose inputs/runtime changed.

## 15. Adding another mesh/resource

For a new mesh:

1. add `configs/resources/<mesh>.yaml` describing the logical resource;
2. add or adapt the runnable case YAML with mesh-specific ranks/static settings;
3. add site-profile resolution only for actual machine policy, not a developer's
   private directory;
4. verify partitions, vertical-level assumptions and static files;
5. reuse scientific fragments only after reviewing their assumptions;
6. add composition/resource/doctor tests;
7. run the complete JACI/system smoke.

Do not copy x1.10242 sampling sizes, vertical levels, partitions or static files
without checking compatibility.

## 16. Local scientific overrides

Do not edit committed files merely to change personal roots. Physical-path
changes belong to the user/site resolution layer.

For an intentional scientific experiment, create a case that includes the
official case and overrides only the required scientific/runtime mapping:

```yaml
# configs/jaci-x1.10242-experiment.yaml
include: jaci-x1.10242.yaml

pbs:
  walltime:
    bmatrix: "04:00:00"
```

Because lists are atomic, overriding `controls`, `relations`, `points` or
`background_variables` requires repeating the complete intended list.

## 17. Related documents

- [`getting-started.md`](getting-started.md): first-run operator flow;
- [`resolution-model.md`](resolution-model.md): source precedence and
  non-standard layouts;
- [`configuration-audit.md`](configuration-audit.md): historical configuration
  audit;
- [`configuration-reorganization.md`](configuration-reorganization.md):
  configuration ownership and prior corrections;
- [`end-to-end-tutorial.md`](end-to-end-tutorial.md): complete system acceptance
  test.
