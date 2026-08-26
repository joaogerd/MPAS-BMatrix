# Getting started on JACI

This guide is the recommended first contact with `MPAS-BMatrix`.

The normal user chooses a site and, when necessary, a workspace. MPAS-BMatrix
then resolves the selected site/resource configuration and shows exactly which
paths will be used. It does not require a beginner to export a wall of path
variables.

Automatic resolution does not mean hidden configuration. Use `mpas-bmatrix
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

The site profile selects the default logical resource (`x1.10242`) and the
default user workspace:

```text
/p/projetos/monan_das/<USER>/work/MPAS-BMatrix
```

To use another work area:

```bash
mpas-bmatrix setup --site jaci --workspace /path/to/my/workspace
```

The semantic user choices are stored in:

```text
~/.config/mpas-bmatrix/setup.yaml
```

A standard setup looks like:

```yaml
site: jaci
workspace: /p/projetos/monan_das/<USER>/work/MPAS-BMatrix
resource: x1.10242
```

The file does not duplicate the scientific stage configuration. Additional
physical paths are written only when the user explicitly requests a non-standard
override.

`setup` does not silently download scientific data or create fake placeholder
resources.

## 4. Site profile versus resource catalog

MPAS-BMatrix now separates machine policy from scientific resource identity:

```text
user setup
   +
site profile
   +
resource catalog
   ↓
resolved configuration
   ↓
doctor
```

The JACI machine-resolution rules live in:

```text
configs/sites/jaci.yaml
```

The logical x1.10242 resource contract lives in:

```text
configs/resources/x1.10242.yaml
```

The resource catalog describes **what** x1.10242 contains (mesh identity,
vertical levels, static files and runtime prerequisites). It deliberately does
not decide **where** a particular user stores those files.

See [`resolution-model.md`](resolution-model.md) for the complete model.

## 5. What happens when a user has a different layout

A normal, fully provisioned site user should not configure infrastructure paths.
If a user intentionally has a private/non-standard installation, configure only
the roots that differ.

For example:

```bash
mpas-bmatrix setup --site jaci \
  --monan-jedi-install /custom/install/monan-jedi
```

Other advanced setup overrides are available when needed:

```text
--mesh-root
--static-root
--monan-jedi-source
--stack-root
```

The corresponding values are persisted under an explicit `overrides:` section
in the user's setup file. Environment variables remain available for one-off or
developer overrides.

The resolver does not recursively search arbitrary project directories.

## 6. Current resolution precedence

For runtime roots:

```text
explicit environment override
        ↓
saved user override
        ↓
canonical path from the site profile (when published)
        ↓
command probe from the active environment
        ↓
compatibility fallback
        ↓
unresolved
```

For the workspace:

```text
explicit setup argument
        ↓
WORK_ROOT environment override
        ↓
saved user workspace
        ↓
site-profile default
```

The current JACI profile still contains per-user compatibility candidates because
a canonical shared MONAN-JEDI/resource publication has not yet been established.
When one is used, `paths` reports it explicitly as:

```text
source: compatibility-fallback
```

This is a transitional state, not a claim that the private path is the official
site contract.

## 7. See exactly what will be used

```bash
mpas-bmatrix paths
```

The command shows:

- selected site and logical resource;
- site-profile file;
- resource-catalog file;
- each resolved physical path and its role;
- the source of each resolution decision;
- warnings when compatibility fallbacks are being used.

Example source labels include:

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

For machine-readable output:

```bash
mpas-bmatrix paths --json
```

## 8. Validate before running

Run:

```bash
mpas-bmatrix doctor
```

The command validates the selected resource contract and concrete prerequisites,
including the current x1.10242 requirements:

```text
mesh identity and configured vertical levels
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

Executables must exist as files and have execute permission. Other filesystem
prerequisites must exist at the resolved locations.

`READY` means the **resolved preflight prerequisites** are present. It does not
mean that the complete PBS/end-to-end scientific chain has already been run.
That remains a separate acceptance test.

## 9. Inspect configuration

```bash
mpas-bmatrix check-config
```

This validates composition of the YAML/scientific contract and prints:

```text
Configuration status: VALID
Runtime readiness: NOT CHECKED by this command; run 'mpas-bmatrix doctor'.
```

This distinction avoids confusing a syntactically/compositionally valid config
with an operationally ready runtime.

For the complete composed configuration:

```bash
mpas-bmatrix check-config --json
```

## 10. Workspace and products

The stable parent layout created by `setup` is:

```text
<WORK_ROOT>/
└── bmatrix/
    ├── bflow_preprocessing/
    ├── covariance/
    └── plots/
```

For a BFLOW range, the run workspace is deterministic:

```text
<WORK_ROOT>/bmatrix/bflow_preprocessing/np<NPROC>_<START>_<END>/
```

Covariance stages use the same run name below:

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

## 11. Transitional dependency and target state

Two parts of the current x1.10242 deployment remain transitional:

1. physical mesh/static roots may still resolve through existing JACI user-area
   compatibility conventions;
2. `geovars.yaml` and `keptvars.yaml` are still read from a MONAN-JEDI source
   checkout.

The target infrastructure is a versioned, validated shared JACI resource bundle
plus a canonical site runtime publication. Once those exist, the JACI profile can
replace compatibility fallbacks with stable `site-profile` paths without changing
the scientific resource catalog or the normal user commands.
