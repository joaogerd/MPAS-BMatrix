# Getting started on JACI

This guide is the recommended first contact with `MPAS-BMatrix`.

The goal is simple: a normal user chooses **where the experiment work will
live**, while MPAS-BMatrix resolves known JACI software and data locations,
validates them and shows exactly what will be used.

Automatic discovery does not mean hidden configuration. Use `mpas-bmatrix
paths`, `doctor` and `check-config --json` to inspect every resolved path and
configuration value.

## 1. What MPAS-BMatrix does

MPAS-BMatrix starts from same-valid-time NMC forecast pairs and runs:

```text
mpaswf -> BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

`mpaswf` owns upstream GFS/WPS, MPAS initialization and forecasts.
`MPAS-BMatrix` owns the B-matrix workflow from BFLOW onward.

## 2. Install

```bash
git clone https://github.com/joaogerd/MPAS-BMatrix.git
cd MPAS-BMatrix
python -m pip install -e .
```

The public command is:

```bash
mpas-bmatrix
```

Normal user documentation uses this command. `PYTHONPATH=src` and `python -m
bmatrix` are developer/debug interfaces.

## 3. First setup

On JACI:

```bash
mpas-bmatrix setup --site jaci
```

The default user workspace is:

```text
/p/projetos/monan_das/<USER>/work/MPAS-BMatrix
```

To use another work area:

```bash
mpas-bmatrix setup --site jaci --workspace /path/to/my/workspace
```

The current pipeline stores runs below:

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

`setup` creates the stable parent directories used by this layout. Individual
run directories are created deterministically when a build starts.

The user choice (`site` and `workspace`) is stored in:

```text
~/.config/mpas-bmatrix/setup.yaml
```

This file contains **only user choices**. It does not duplicate scientific
configuration or machine resource paths.

`setup` does not silently download scientific data or create fake placeholder
resources.

## 4. What MPAS-BMatrix resolves automatically

For the current JACI x1.10242 case the CLI resolves these concepts:

| Resource | What it represents | Why it is needed |
| --- | --- | --- |
| MPAS-BMatrix repository | Code, configuration and PBS templates | Render and orchestrate stages |
| User workspace | Persistent area owned by the user | Store BFLOW, covariance and plot workspaces |
| MONAN-JEDI install | Installed MPAS-JEDI/SABER executables and `share/` runtime files | Run covariance and validation stages |
| MPAS mesh root | `x1.10242.grid.nc`, graph and MPI partitions | Define MPAS horizontal geometry |
| Static root | Invariant, namelist, streams and stream lists | Provide mesh/runtime static inputs |
| MONAN-JEDI source | Current location of `geovars.yaml` and `keptvars.yaml` | Transitional dependency only |
| spack-stack root | JACI MPAS-JEDI runtime environment | Load compiler/MPI/libraries in PBS jobs |

The current discovery order is:

```text
explicit command argument (when available)
        ↓
explicit environment override
        ↓
known command/site discovery
        ↓
safe site default
        ↓
unresolved -> doctor reports the missing resource
```

An explicit environment variable remains supported for advanced/non-standard
installations, but it is no longer the normal first-step interface.

## 5. Validate before running

Run:

```bash
mpas-bmatrix doctor
```

The command checks concrete resources, including:

```text
MPAS-JEDI installation prefix
mpasjedi_error_covariance_toolbox.x
mpasjedi_variational.x
mpasjedi_unbalance_ensemble.x
MPAS core_atmosphere share directory
x1.10242.grid.nc
x1.10242.graph.info
x1.10242.graph.info.part.128
x1.10242.invariant.nc
namelist.atmosphere_240km
streams.atmosphere_240km
stream_list.atmosphere.analysis
stream_list.atmosphere.background
stream_list.atmosphere.ensemble
geovars.yaml
keptvars.yaml
MPAS physics tables
spack-stack root
```

A missing item is reported by name, path and role.

Do not start a PBS sequence until `doctor` ends with:

```text
READY
```

## 6. See exactly what will be used

```bash
mpas-bmatrix paths
```

This prints each resolved path and explains its role.

It also reports how each root was obtained, for example:

```text
MONAN_JEDI_INSTALL: /path/to/install
  source: discovered

WORK_ROOT: /p/projetos/monan_das/<USER>/work/MPAS-BMatrix
  source: site-default
```

For machine-readable output:

```bash
mpas-bmatrix paths --json
```

## 7. Inspect configuration without reading a JSON dump

```bash
mpas-bmatrix check-config
```

The default output is a short operator summary containing site, mesh, MPI ranks,
workspace, configuration sources and validation status.

For the complete composed configuration:

```bash
mpas-bmatrix check-config --json
```

The JSON form is intended for debugging, audit and reproducibility records.

## 8. Where products appear

For a BFLOW range, the first workspace is deterministic:

```text
<WORK_ROOT>/bmatrix/bflow_preprocessing/np<NPROC>_<START>_<END>/
```

Covariance stages then use the same run name below:

```text
<WORK_ROOT>/bmatrix/covariance/vbal/<RUN>/
<WORK_ROOT>/bmatrix/covariance/unbalance/<RUN>/
<WORK_ROOT>/bmatrix/covariance/hdiag/<RUN>/
<WORK_ROOT>/bmatrix/covariance/nicas/<RUN>/
<WORK_ROOT>/bmatrix/covariance/so/<RUN>/
<WORK_ROOT>/bmatrix/covariance/dirac/<RUN>/
```

Plots are written below:

```text
<WORK_ROOT>/bmatrix/plots/<RUN>/
```

The exact scientific products inside each stage are documented in
[`stage-products.md`](stage-products.md).

For reusable B-matrix products associated with an existing BFLOW workspace:

```bash
mpas-bmatrix products --bflow-workspace /path/to/BFLOW_WORKSPACE
```

## 9. Advanced overrides

The automatic resolver is not a lock-in. Advanced users may override a
non-standard installation with:

```text
WORK_ROOT
MONAN_JEDI_INSTALL
MPAS_MESH_ROOT
MPAS_JEDI_STATIC_ROOT
MONAN_JEDI_SOURCE
STACK_ROOT
BMATRIX_ROOT        (rare; normally derived automatically)
```

The separate `MONAN_JEDI_UNBALANCE_EXE` variable is no longer needed for the
standard JACI installation. The executable is derived as:

```text
<MONAN_JEDI_INSTALL>/bin/mpasjedi_unbalance_ensemble.x
```

## 10. Transitional resources and next step

Two parts of the current x1.10242 case are still transitional:

1. mesh/static data are discovered from existing JACI user-area conventions;
2. `geovars.yaml` and `keptvars.yaml` are still read from a MONAN-JEDI source checkout.

The next infrastructure step is a versioned, validated x1.10242 **resource
bundle** in a shared JACI location. Once that bundle exists, a normal user will
no longer need a private mesh/static copy or a MONAN-JEDI source checkout just
to run MPAS-BMatrix.
