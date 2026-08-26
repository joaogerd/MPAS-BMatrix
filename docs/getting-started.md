# Getting started on JACI

This guide is the recommended first contact with `MPAS-BMatrix`.

The goal is simple: a normal user should choose **where the experiment work will
live**, while MPAS-BMatrix resolves the known JACI software and data locations,
validates them and shows exactly what will be used.

The workflow remains transparent. Automatic discovery does not mean hidden
configuration: use `mpas-bmatrix paths`, `doctor` and `check-config --json` to
inspect every resolved path and configuration value.

## 1. What MPAS-BMatrix does

MPAS-BMatrix starts from same-valid-time NMC forecast pairs and runs:

```text
mpaswf -> BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

`mpaswf` owns the upstream GFS/WPS, MPAS initialization and forecasts.
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

Normal user documentation should use this command. `PYTHONPATH=src` and
`python -m bmatrix` are developer/debug interfaces, not the standard workflow.

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

`setup` creates only the user workspace structure:

```text
MPAS-BMatrix/
├── config/    user/run configuration snapshots
├── data/      persistent user-owned input/intermediate data
├── work/      stage execution workspaces
├── output/    reusable/final products
└── logs/      operational logs and diagnostics
```

It also stores the minimal user selection (`site` and `workspace`) in:

```text
~/.config/mpas-bmatrix/setup.yaml
```

It does **not** copy scientific data, silently download software or create fake
placeholder resources.

## 4. What MPAS-BMatrix resolves automatically

For the current JACI x1.10242 case the CLI resolves these concepts:

| Resource | What it represents | Why it is needed |
| --- | --- | --- |
| MPAS-BMatrix repository | Code, configuration and PBS templates for this workflow | Render and orchestrate all stages |
| User workspace | Persistent area owned by the user | Store workspaces, products and logs |
| MONAN-JEDI install | Installed MPAS-JEDI/SABER executables and `share/` runtime files | Run VBAL/HDIAG/NICAS/SO/DIRAC |
| MPAS mesh root | `x1.10242.grid.nc`, graph and MPI partitions | Define the MPAS horizontal geometry |
| Static root | Invariant, namelist, streams and related static files | Initialize compatible MPAS-JEDI geometry/runtime |
| MONAN-JEDI source | Current location of `geovars.yaml` and `keptvars.yaml` | Transitional dependency; planned for removal |
| spack-stack root | JACI MPAS-JEDI runtime environment | Load compiler/MPI/libraries inside PBS jobs |

The current discovery order is:

```text
explicit environment override
        ↓
known command/site discovery
        ↓
site default (when one is safe)
        ↓
unresolved -> doctor reports the missing resource
```

An explicit environment variable is therefore still supported for advanced or
non-standard installations, but it is no longer the normal first-step interface.

## 5. Validate before running

Run:

```bash
mpas-bmatrix doctor
```

The command checks the resolved configuration and concrete files, including:

```text
MPAS-JEDI installation
mpasjedi_error_covariance_toolbox.x
mpasjedi_variational.x
mpasjedi_unbalance_ensemble.x
x1.10242.grid.nc
x1.10242.graph.info
x1.10242.graph.info.part.128
x1.10242.invariant.nc
static files directory
geovars.yaml
keptvars.yaml
spack-stack root
```

A missing path is reported as a missing resource rather than as an unexplained
`${VARIABLE}` substitution error.

Do not start a PBS sequence until `doctor` ends with:

```text
READY
```

## 6. See exactly what will be used

```bash
mpas-bmatrix paths
```

This prints the resolved path plus the role of each resource.

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

## 8. Where outputs appear

The stage paths are deterministic below the configured work root. The current
BFLOW convention starts at:

```text
<WORK_ROOT>/bmatrix/bflow_preprocessing/np<NPROC>_<START>_<END>/
```

Downstream stages derive their own deterministic workspaces from this run.
Use the existing `products` command for reusable B-matrix products and the stage
product guide for the meaning and acceptance criteria of each file:

```bash
mpas-bmatrix products ...
```

See [`stage-products.md`](stage-products.md).

## 9. Advanced overrides

The automatic resolver is not a lock-in. Advanced users may still override a
non-standard installation with environment variables such as:

```text
WORK_ROOT
MONAN_JEDI_INSTALL
MPAS_MESH_ROOT
MPAS_JEDI_STATIC_ROOT
MONAN_JEDI_SOURCE
STACK_ROOT
```

`BMATRIX_ROOT` is normally derived from the installed/checked-out package and
should not need to be set.

The separate `MONAN_JEDI_UNBALANCE_EXE` variable is no longer needed for the
standard JACI installation: the executable is derived as:

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
