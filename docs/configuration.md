# Configuration guide

MPAS-BMatrix composes machine/runtime, mesh/case, and scientific-stage YAMLs.

## Configuration hierarchy

```text
configs/jaci.yaml
  JACI runtime base

configs/jaci-x1.10242.yaml
  runnable mesh/case; includes jaci.yaml

configs/bmatrix-x1.10242.yaml
  scientific-contract aggregator

configs/bmatrix/x1.10242/*.yaml
  controls and stage-specific scientific fragments
```

Users normally pass only:

```bash
mpas-bmatrix check-config --config configs/jaci-x1.10242.yaml
```

## Required environment variables

For the standard x1.10242 JACI case:

```bash
export BMATRIX_ROOT=/path/to/projects/MPAS-BMatrix
export WORK_ROOT=/path/to/work/MPAS-BMatrix

export MONAN_JEDI_INSTALL_ROOT=/p/projetos/monan_das/$USER/build/monan-jedi

export MPAS_MESH_ROOT=/path/to/mpas_meshes
export MPAS_JEDI_STATIC_ROOT=/path/to/validated/x1.10242/static-files
export STACK_ROOT=/path/to/spack-stack
```

The normal runtime configuration does not need:

```text
MONAN_JEDI_SOURCE
MONAN_JEDI_UNBALANCE_EXE
```

The historical `MONAN_JEDI_INSTALL` variable is accepted as a compatibility
alias if `MONAN_JEDI_INSTALL_ROOT` is not defined.

## MONAN-JEDI runtime ownership

`configs/jaci.yaml` defines one install root:

```yaml
install:
  root: ${MONAN_JEDI_INSTALL_ROOT}
  atmosphere_share: ${MONAN_JEDI_INSTALL_ROOT}/share/MPAS/core_atmosphere
```

Executables are derived conventionally from `install.root/bin`, including:

```text
mpasjedi_error_covariance_toolbox.x
mpasjedi_variational.x
mpasjedi_unbalance_ensemble.x
```

The x1.10242 case consumes MPAS-JEDI runtime YAMLs installed by MONAN-JEDI:

```yaml
static:
  geovars: ${MONAN_JEDI_INSTALL_ROOT}/share/monan-jedi/mpas-jedi/namelists/geovars.yaml
  keptvars: ${MONAN_JEDI_INSTALL_ROOT}/share/monan-jedi/mpas-jedi/namelists/keptvars.yaml
```

Consumers must not depend on the MONAN-JEDI source checkout or private work/build
trees.

## Case/static inputs

`MPAS_JEDI_STATIC_ROOT` remains separate from the compiled installation because
it describes the validated scientific case. It should contain the required
invariant and reference atmosphere files, for example:

```text
x1.10242.invariant.nc
namelist.atmosphere_240km
streams.atmosphere_240km
stream_list.atmosphere.*
```

Likewise, mesh and partition files are declared through `MPAS_MESH_ROOT`.

## PBS environment

Variables needed before `scripts/load_jaci_env.sh` runs inside a PBS job belong
under `environment.variables`:

```yaml
environment:
  loader: scripts/load_jaci_env.sh
  variables:
    STACK_ROOT: ${STACK_ROOT}
```

The scheduler writes them explicitly into generated scripts instead of depending
on arbitrary login-shell inheritance.

## Include semantics

A YAML may include one file:

```yaml
include: jaci.yaml
```

or several:

```yaml
include:
  - controls.yaml
  - bflow.yaml
  - vbal.yaml
```

Rules:

1. paths are relative to the declaring YAML;
2. files merge in declaration order;
3. the declaring file overrides included mappings;
4. nested mappings merge recursively;
5. lists are atomic and are replaced as complete units;
6. cyclic includes are rejected;
7. unresolved environment references are rejected.

## Where a value belongs

| Change | Owner |
| --- | --- |
| MONAN/MPAS/JEDI executables and installed runtime support | `MONAN_JEDI_INSTALL_ROOT` / MONAN-JEDI |
| JACI queue, walltime or environment loader | `configs/jaci.yaml` |
| MPAS mesh, partitions, vertical levels, invariant/reference case | `configs/jaci-x1.10242.yaml` |
| NMC/BFLOW preprocessing | `configs/bmatrix/x1.10242/bflow.yaml` |
| Controls and aliases | `configs/bmatrix/x1.10242/controls.yaml` |
| Vertical-balance calibration | `configs/bmatrix/x1.10242/vbal.yaml` |
| K2^-1/unbalance scientific read flags | `configs/bmatrix/x1.10242/unbalance.yaml` |
| HDIAG | `configs/bmatrix/x1.10242/hdiag.yaml` |
| NICAS | `configs/bmatrix/x1.10242/nicas.yaml` |
| Single-observation validation | `configs/bmatrix/x1.10242/so.yaml` |
| DIRAC | `configs/bmatrix/x1.10242/dirac.yaml` |

## UNBALANCE executable

The executable is infrastructure, not a scientific parameter. The normal path is
resolved automatically as:

```text
${MONAN_JEDI_INSTALL_ROOT}/bin/mpasjedi_unbalance_ensemble.x
```

The scientific UNBALANCE fragment should therefore describe only the BUMP/K2^-1
contract.

The implementation still accepts an explicit executable in older custom configs,
but the standard JACI configuration no longer requires one.

## Rebuild rules

A scientific change invalidates that stage and all downstream stages:

```text
BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

Run from the earliest invalid stage with `--clean`.

## Adding another mesh/case

Create a new platform/case YAML and, when needed, a new scientific-fragment tree.
Do not reuse x1.10242 partition counts, vertical levels, sampling sizes or static
inputs without checking compatibility.

## Local overrides

Prefer environment variables for machine-specific roots. For intentional
experiments, create an overlay YAML that includes the official case and overrides
only the required mapping. Remember that lists are atomic.

## Validation

After changing configuration:

```bash
mpas-bmatrix check-config --config configs/jaci-x1.10242.yaml
```

The resolved output records `configuration_sources`, `bmatrix_contract_path`, and
`bmatrix_contract_sources`. Any unresolved `${VARIABLE}` is rejected before a
PBS job is generated.
