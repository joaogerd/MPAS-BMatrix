# Refactoring notes

This document summarizes the main architectural decisions in the refactored
`mpas-bmatrix-global` package.

## Public interface

The package has one installed public entry point:

```bash
mpas-bmatrix
```

The CLI subcommands are:

```text
check-config
weights
build
validate
plots
products
```

## Orchestration

`bmatrix.pipeline` owns the dependency-ordered production stage graph:

```text
BFLOW -> VBAL -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

The pipeline is resumable through `--from-stage` and `--to-stage`. `--dry-run`
returns a plan without touching the filesystem, importing heavy NetCDF/ESMPy
dependencies or submitting PBS jobs.

## Stage ownership

- `bflow_core`: prepares FULL/PTB products from existing NMC pairs.
- `vbal_core`: renders/runs/validates vertical-balance calibration.
- `hdiag_core`: applies inverse VBAL in memory and computes standard deviation
  and correlation diagnostics.
- `nicas_core`: computes and merges NICAS products.
- `so_core`: validates the complete B in a single-observation variational run.
- `dirac_core`: produces the complete-B impulse-response product.
- `plots_core`: generates local diagnostic plots from completed NetCDF products.
- `scheduler`: centralizes PBS submission and progress display.
- `unbalance_core`: retained legacy diagnostic path used only for A/B regression
  validation of the former materialized workflow.

## Important changes from the original scripts

- The B-matrix package no longer owns WPS, MPAS initialization or MPAS forecast
  integration. Those are upstream responsibilities, currently handled by
  `mpaswf`.
- ESMPy weight generation is internal to the package; there is no NCL or SCRIP
  executable requirement.
- BFLOW, VBAL and HDIAG use file names declared in `bflow.products`.
- VBAL and HDIAG render YAML from the scientific control contract instead of
  hard-coded tutorial names.
- VBAL no longer relies on `background error.output ensemble`.
- HDIAG rereads the original staged NMC perturbations and applies
  `BUMP_VerticalBalance` as an outer block, so `K2^-1` is evaluated in memory
  before BUMP_NICAS diagnostics.
- The production workflow does not require `samplesUnbalanced` or
  `mpasjedi_unbalance_ensemble.x`.
- `unbalance_core` is deliberately outside `bmatrix.pipeline.STAGES` and remains
  only until the direct VBAL-to-HDIAG path is validated A/B against the previous
  implementation.
- NICAS local reads in SO/DIRAC split 3D and 2D groups to avoid `nl0`
  dimensionality errors.
- SO and DIRAC use aliases for JEDI/SABER/BUMP product reads but keep MPAS
  stream files MPAS-native.
- DIRAC is represented as a first-class stage and produces `mpas.dirac.nc`.
- PLOTS is represented as a local post-processing stage after DIRAC.

## Maintained invariants

Do not change these without a new end-to-end validation:

1. one public command: `mpas-bmatrix`;
2. direct production dependency `VBAL -> HDIAG`;
3. HDIAG applies inverse vertical balance in memory before BUMP_NICAS
   diagnostics;
4. canonical `in code` names plus NetCDF `in file` aliases;
5. split NICAS read grids for 3D controls and 2D surface pressure;
6. MPAS-native output streams for SO/DIRAC;
7. DIRAC contract based on full `dirLats`/`dirLons` plus singular selectors;
8. persistent audits outside `/tmp`;
9. CDF5 validation for final NetCDF products.

See [`in-memory-vbal-hdiag.md`](in-memory-vbal-hdiag.md) for the migration A/B
acceptance procedure.
