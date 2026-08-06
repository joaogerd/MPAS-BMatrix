# Software architecture

This document describes the internal structure of `MPAS-BMatrix` for developers.
Users who only need to run the workflow should start with
[`user-guide.md`](user-guide.md).

## 1. Architectural principles

1. **One public command:** `mpas-bmatrix`.
2. **Explicit scientific order:** later stages may run only after their required
   upstream products are valid.
3. **Stage-local ownership:** each stage owns its preparation, execution and
   validation logic.
4. **Product contracts:** documented files and manifests connect stages.
5. **Composed configuration:** site, mesh/case and scientific-stage settings are
   maintained separately but resolved into one mapping before execution.
6. **No hidden upstream workflow:** GFS/WPS/MPAS forecast generation belongs to
   `mpaswf`; this repository starts at BFLOW.

## 2. Stage graph

```text
External:
  mpaswf -> forecast-pair manifest

MPAS-BMatrix:
  BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

The ordered stage tuple is defined in `src/bmatrix/pipeline.py`. The same module
implements `--from-stage`, `--to-stage`, deterministic workspace resolution and
sequential validation.

## 3. Public interface

```text
src/bmatrix/cli.py
```

Responsibilities:

- parse command-line options;
- load the composed configuration;
- create a `BuildRequest`;
- delegate to pipeline or plotting functions;
- convert known workflow errors into a nonzero exit status.

Public subcommands:

```text
check-config
weights
build
validate
plots
products
```

The CLI should remain thin. Scientific logic belongs in stage modules or shared
scientific accessors.

## 4. Configuration architecture

The runnable x1.10242 case is composed as follows:

```text
configs/jaci.yaml
  JACI site/runtime/build base
        ↓ include
configs/jaci-x1.10242.yaml
  x1.10242 mesh/static case and bmatrix.configuration
        ↓ reference
configs/bmatrix-x1.10242.yaml
  scientific-contract aggregator
        ↓ include
configs/bmatrix/x1.10242/*.yaml
  control registry and one fragment per stage
```

Implementation:

```text
src/bmatrix/config.py
```

- reads YAML mappings;
- resolves recursive `include` declarations;
- rejects include cycles;
- expands environment variables;
- deep-merges mappings;
- treats lists as atomic values;
- loads `bmatrix.configuration` after composing the platform/case;
- records platform and scientific source-file provenance.

```text
src/bmatrix/scientific_config.py
```

- validates stage sections and control definitions;
- translates canonical JEDI names to NetCDF file names;
- builds simple and compound aliases;
- enforces 3D/2D NICAS grouping;
- validates analysis/background variable coverage;
- resolves BFLOW product names.

Stage code consumes the final merged mapping and does not need to know which YAML
fragment declared a value.

## 5. Main orchestration modules

```text
src/bmatrix/pipeline.py
```

Defines:

- `STAGES` and `StageName`;
- `BuildRequest`;
- deterministic `PipelinePaths`;
- dry-run planning;
- stage-by-stage build and validation dispatch.

```text
src/bmatrix/products.py
```

Resolves the reusable final product set from stage workspaces.

```text
src/bmatrix/scheduler.py
```

Defines scheduler-independent job/resource models and renders PBS Pro scripts.
The scheduler obtains queue, walltime, MPI ranks and the repository-local
environment loader from the composed configuration.

## 6. Stage modules

```text
src/bmatrix/bflow_core/
```

Consumes an external manifest or deterministic forecast paths. Owns pair
resolution, ESMF weights, wind transformation, derived variables, FULL/PTB
products and BFLOW validation.

```text
src/bmatrix/vbal_core/
```

Stages BFLOW perturbations, static MPAS files and renders/submits/validates VBAL
calibration.

```text
src/bmatrix/unbalance_core/
```

Applies K2^-1 to centered members and materializes `samplesUnbalanced` for
HDIAG. The executable is resolved from platform/build configuration.

```text
src/bmatrix/hdiag_core/
```

Renders/submits/validates standard-deviation and correlation diagnostics. It
also validates the configured distance-bin extent before submission.

```text
src/bmatrix/nicas_core/
```

Calibrates NICAS per control, creates local/global products and merges variables
into reusable complete products.

```text
src/bmatrix/so_core/
```

Renders/submits/validates the complete-B single-observation variational test.

```text
src/bmatrix/dirac_core/
```

Renders/submits/validates the complete-B impulse-response test.

```text
src/bmatrix/plots_core/
```

Runs local post-processing and plotting without PBS submission or modification
of scientific NetCDF products.

## 7. Stage lifecycle

A scheduler-backed stage normally follows:

```text
resolve upstream products
  -> create/clean deterministic workspace
  -> stage static and dynamic inputs
  -> render JEDI/SABER YAML and PBS script
  -> submit and wait
  -> validate logs and output files
  -> expose products to the next stage
```

PLOTS follows the same resolve/validate contract but executes locally.

## 8. Product interfaces

```text
BFLOW -> VBAL
  manifest.tsv
  output/*/PTB_f48mf24.nc
  output/*/FULL_f24.nc

VBAL -> UNBALANCE
  mpas_vbal.nc
  mpas_sampling.nc
  local VBAL/sampling products
  staged samples

UNBALANCE -> HDIAG
  samplesUnbalanced/PTB_f48mf24_*.nc

HDIAG -> NICAS
  mpas.stddev.nc
  mpas.cor_rh.nc
  mpas.cor_rv.nc

NICAS -> SO/DIRAC
  merge/mpas_nicas.nc
  local NICAS and grid products

SO/DIRAC/other products -> PLOTS
  completed validation and diagnostic products
```

See [`stage-products.md`](stage-products.md) for user-facing acceptance criteria.

## 9. Generated YAML and PBS

Generated stage YAML is a reproducibility artifact. It should contain no
unexplained hard-coded scientific choices that belong in configuration.

When changing a renderer:

1. identify whether the value is platform, mesh/case, scientific or run-specific;
2. place persistent values in the correct configuration layer;
3. add validation/accessor logic;
4. update rendering tests;
5. update inline YAML comments and configuration documentation;
6. run a stage smoke test on JACI.

## 10. Adding a stage

A new stage requires:

1. a stage-local package under `src/bmatrix/<stage>_core/`;
2. input and output product contracts;
3. deterministic workspace resolution;
4. preparation, execution/submission and validation functions;
5. insertion into `StageName`, `STAGES` and pipeline dispatch;
6. a documented scientific fragment if it has persistent scientific settings;
7. unit tests for configuration, rendering and ordering;
8. user/developer documentation and rebuild rules.

Do not place stage-specific scientific parameters in `configs/jaci.yaml` or
`configs/jaci-x1.10242.yaml`.
