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

For the shipped x1.10242 JACI case, the configuration itself contains the
`$USER`-based project/work, mesh and static-data paths. The environment
variables that must be set before `check-config` are:

```bash
export MONAN_JEDI_INSTALL_ROOT=/p/projetos/monan_das/$USER/build/monan-jedi
export STACK_ROOT=/path/to/validated/spack-stack
```

`MONAN_JEDI_INSTALL_ROOT` selects the installed MPAS/JEDI runtime.
`STACK_ROOT` is propagated into generated PBS scripts through
`environment.variables.STACK_ROOT`, so batch jobs load the same stack selected
for the login shell.

`BMATRIX_ROOT` and `WORK_ROOT` are useful shell conveniences in tutorials,
but they are not configuration inputs unless a custom overlay references them.
The current shipped case also does not consume `MPAS_MESH_ROOT` or
`MPAS_JEDI_STATIC_ROOT`; mesh/static paths are explicit in
`configs/jaci-x1.10242.yaml`.

The normal production configuration does not need:

```text
MONAN_JEDI_SOURCE
MONAN_JEDI_UNBALANCE_EXE
```

The historical `MONAN_JEDI_INSTALL` variable is accepted as a compatibility
alias if `MONAN_JEDI_INSTALL_ROOT` is not defined and emits a deprecation
warning. New scripts must export only `MONAN_JEDI_INSTALL_ROOT`.

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
login-shell inheritance. The maintained JACI base maps
`environment.variables.STACK_ROOT` to `${STACK_ROOT}`, making the selected
stack an explicit run-time input instead of a personal hardcoded path.

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

`check-config` is a side-effect-free preflight. In addition to composing the
YAML, it verifies the public MONAN-JEDI install, required JEDI/SABER executables,
MPAS runtime share directory, selected `STACK_ROOT`, stack setup/module tree,
repository loader, work-area writability, mesh/partition, invariant and installed
MPAS-JEDI namelists. Missing mandatory resources make the command return non-zero
before any scientific job is rendered or submitted.

The JSON output preserves the resolved configuration and adds a `preflight`
section with per-resource status. It also records `configuration_sources`,
`bmatrix_contract_path`, and `bmatrix_contract_sources`. Any unresolved
`${VARIABLE}` is rejected before filesystem validation.


### Physical preflight details

The preflight requires the resources needed by the maintained production chain:
the MPAS grid and graph, the partition directory and rank-matched partition,
the invariant state, tutorial/runtime support directory, `geovars.yaml` and
`keptvars.yaml`. Omitted mandatory entries are reported as `NOT_CONFIGURED`.

The partition filename is derived from the configured graph basename exactly as
the VBAL static staging code does: `<graph basename>.part.<mesh.nproc>`.

For `STACK_ROOT`, the preflight follows the loader contract and accepts either
the spack-stack checkout itself or its immediate parent containing a
`spack-stack/` child.
