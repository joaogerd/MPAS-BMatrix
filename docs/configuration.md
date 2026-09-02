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
  controls and scientific fragments
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

The normal production configuration does not need:

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

Production executables are derived conventionally from `install.root/bin`:

```text
mpasjedi_error_covariance_toolbox.x
mpasjedi_variational.x
```

`mpasjedi_unbalance_ensemble.x` is not required by the production stage graph.
It is retained only for the temporary legacy A/B comparison path.

The x1.10242 case consumes MPAS-JEDI runtime YAMLs installed by MONAN-JEDI.
Consumers must not depend on the MONAN-JEDI source checkout or private
work/build trees.

## Case/static inputs

`MPAS_JEDI_STATIC_ROOT` describes the validated scientific case and should
contain the required invariant and reference atmosphere files. Mesh and
partition files are declared through `MPAS_MESH_ROOT`.

## PBS environment

Variables needed before `scripts/load_jaci_env.sh` runs inside a PBS job belong
under `environment.variables`; generated scripts must not depend on arbitrary
login-shell inheritance.

## Include semantics

A YAML may include one or several files. Paths are relative to the declaring
YAML, mappings merge recursively, lists are replaced atomically, cycles are
rejected and unresolved environment references fail before execution.

## Where a value belongs

| Change | Owner |
| --- | --- |
| MONAN/MPAS/JEDI executables and installed runtime support | `MONAN_JEDI_INSTALL_ROOT` / MONAN-JEDI |
| JACI queue, walltime or environment loader | `configs/jaci.yaml` |
| MPAS mesh, partitions, vertical levels, invariant/reference case | `configs/jaci-x1.10242.yaml` |
| NMC/BFLOW preprocessing | `configs/bmatrix/x1.10242/bflow.yaml` |
| Controls and aliases | `configs/bmatrix/x1.10242/controls.yaml` |
| Vertical-balance calibration | `configs/bmatrix/x1.10242/vbal.yaml` |
| HDIAG and in-memory inverse-VBAL consumption | `configs/bmatrix/x1.10242/hdiag.yaml` plus `vbal.yaml` |
| Legacy materialized K2^-1 A/B reference only | `configs/bmatrix/x1.10242/unbalance.yaml` |
| NICAS | `configs/bmatrix/x1.10242/nicas.yaml` |
| Single-observation validation | `configs/bmatrix/x1.10242/so.yaml` |
| DIRAC | `configs/bmatrix/x1.10242/dirac.yaml` |

## Legacy UNBALANCE configuration

`configs/bmatrix/x1.10242/unbalance.yaml` remains included temporarily so the
previous explicit `K2^-1 -> samplesUnbalanced` implementation can be reproduced
for A/B validation. It is not part of `bmatrix.pipeline.STAGES` and normal
`mpas-bmatrix build` does not execute it.

After the in-memory path passes the documented numerical comparison, this
fragment and `unbalance_core` can be removed in a separate cleanup change.

## Rebuild rules

A scientific change invalidates that stage and all downstream production stages:

```text
BFLOW -> VBAL -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

A VBAL change also changes the transform read by HDIAG, so rerun from VBAL.
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
