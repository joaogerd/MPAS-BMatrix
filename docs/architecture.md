# Software architecture

This document describes the internal structure of `MPAS-BMatrix` for developers.
It is not required reading for users who only need to run the workflow.

## 1. Architectural principles

The codebase follows four principles:

1. **One public command**: the user entry point is `mpas-bmatrix`.
2. **Sequential scientific stages**: the official stage order is explicit.
3. **Stage-local implementation**: each stage owns its own preparation,
   submission and validation logic.
4. **Reusable contracts**: file names, variables, aliases and scientific
   parameters come from configuration and shared helpers, not from ad hoc shell
   scripts.

## 2. Stage graph

Official order:

```text
BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

External upstream:

```text
mpaswf -> forecast-pair manifest -> BFLOW
```

`mpaswf` is not part of this package; it is the upstream MPAS forecast producer.

## 3. Main modules

```text
src/bmatrix/cli.py
```

Defines the public command-line interface. The CLI should remain thin: it parses
arguments, resolves configuration and delegates to the pipeline or stage modules.

```text
src/bmatrix/pipeline.py
```

Defines the ordered stage graph and the orchestration behavior. This is where
stage dependencies and `--from-stage` / `--to-stage` semantics should remain
centralized.

```text
src/bmatrix/products.py
```

Defines or resolves product paths used across stages. Product names must remain
consistent with the scientific contract and user documentation.

```text
src/bmatrix/config*.py
```

Configuration loading, merging and validation utilities. The platform YAML and
scientific YAML should remain separate so that scientific changes do not require
rewriting platform paths or PBS settings.

```text
src/bmatrix/bflow_core/
src/bmatrix/vbal_core/
src/bmatrix/unbalance_core/
src/bmatrix/hdiag_core/
src/bmatrix/nicas_core/
src/bmatrix/so_core/
src/bmatrix/dirac_core/
src/bmatrix/plots_core/
```

Stage-specific implementation. Each stage should own only its own generated
files, local validation and stage-specific logic.

```text
src/bmatrix/scheduler/
```

PBS submission and progress display. Stage modules should avoid duplicating PBS
polling logic.

## 4. Stage lifecycle

A stage normally follows this lifecycle:

```text
resolve inputs
  -> create or clean workspace
  -> link/copy required inputs
  -> render generated YAML/PBS/scripts
  -> submit or run
  -> validate outputs
  -> expose products for downstream stages
```

The lifecycle should be observable through logs and manifests. A user should be
able to determine what happened without reading Python internals.

## 5. Configuration layers

The repository separates platform and scientific configuration:

```text
configs/jaci-x1.10242.yaml
  platform/runtime layer:
    paths, mesh, nproc, PBS, modules, executables, static files

configs/bmatrix-x1.10242.yaml
  scientific layer:
    controls, aliases, dimensions, VBAL, UNBALANCE, HDIAG, NICAS, SO, DIRAC
```

Rules:

- avoid hard-coded user paths in documentation and code;
- keep scientific defaults in the scientific YAML when possible;
- keep environment/PBS/runtime defaults in the platform YAML;
- do not silently concatenate scientific lists during configuration merging.

## 6. Product contracts

Products are the interface between stages. A stage should not require knowledge
of another stage's internal temporary files except for documented products.

Examples:

```text
VBAL -> UNBALANCE:
  mpas_vbal.nc
  mpas_sampling.nc
  local VBAL/sampling products
  staged samples

UNBALANCE -> HDIAG:
  samplesUnbalanced/PTB_f48mf24_*.nc

HDIAG -> NICAS:
  mpas.stddev.nc
  mpas.cor_rh.nc
  mpas.cor_rv.nc

NICAS -> SO/DIRAC:
  merge/mpas_nicas.nc
  merge/mpas_nicas_local_*
  merge/mpas_nicas_grids_local_*
```

See [`stage-products.md`](stage-products.md) for the user-facing product matrix.

## 7. Generated YAML and PBS

Stage modules generate JEDI/SABER YAML and PBS scripts. Those generated files are
part of the reproducibility record.

Guidelines:

- generate deterministic YAML when inputs are unchanged;
- write generated files into the stage workspace;
- keep generated YAML close to the exact executable invocation;
- preserve run logs and stdout/stderr;
- never rely on `/tmp` for persistent stage diagnostics.

## 8. Validation design

Validation should be explicit and stage-specific.

A good validator checks:

```text
- expected files exist;
- files are readable;
- critical dimensions/variables are present;
- logs indicate successful execution when applicable;
- downstream-sensitive invariants are preserved.
```

A validator should not over-interpret scientific quality from a single weak
signal. Example: `an-bg = 0` in MPAS-native SO output fields is not automatically
a failure if the OOPS/JEDI log and obs outputs show a successful single-observation
run.

## 9. Where theory enters the implementation

Scientific meaning is documented in:

```text
bmatrix-theory.md
scientific-contract.md
```

Implementation should reflect those documents through:

```text
- variable lists and aliases;
- VBAL relations;
- UNBALANCE member handling;
- HDIAG sampling and fitting parameters;
- NICAS variable grouping;
- SO and DIRAC B composition;
- Control2Analysis positioning.
```

When code and theory diverge, update both or block the change until the intended
scientific contract is clear.

## 10. Extension points

Common extension points:

| Extension | Likely files/docs to update |
| --- | --- |
| New control variable | scientific YAML, product validation, `scientific-contract.md`, tests |
| New stage | `pipeline.py`, new `*_core`, `user-guide.md`, `stage-products.md`, `developer-guide.md`, tests |
| New plot type | `plots_core`, `diagnostics-and-plots.md`, tests |
| New platform | platform YAML, environment loader docs, quickstart docs |
| New scientific parameter | scientific YAML, `bmatrix-theory.md` or `scientific-contract.md`, tests |

## 11. Anti-patterns

Avoid these patterns:

```text
- adding hidden stage dependencies through temporary files;
- using user-specific absolute paths in committed docs;
- duplicating PBS polling logic in stage modules;
- mixing MPAS-native stream names and canonical JEDI names without aliases;
- assuming VBAL writes the final unbalanced ensemble members;
- treating plotting as a scientific product generator;
- changing stage order without updating documentation and tests.
```
