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

`bmatrix.pipeline` owns the dependency-ordered stage graph:

```text
BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

The pipeline is resumable through `--from-stage` and `--to-stage`. `--dry-run`
returns a plan without touching the filesystem, importing heavy NetCDF/ESMPy
dependencies or submitting PBS jobs.

## Stage ownership

- `bflow_core`: prepares FULL/PTB products from existing NMC pairs.
- `vbal_core`: renders/runs/validates vertical-balance calibration.
- `unbalance_core`: applies `K2^-1` and writes `samplesUnbalanced`.
- `hdiag_core`: computes standard deviation and correlation diagnostics.
- `nicas_core`: computes and merges NICAS products.
- `so_core`: validates the complete B in a single-observation variational run.
- `dirac_core`: produces the complete-B impulse-response product.
- `plots_core`: generates local diagnostic plots from completed NetCDF products.
- `scheduler`: centralizes PBS submission and progress display.

## Important changes from the original scripts

- The B-matrix package no longer owns WPS, MPAS initialization or MPAS forecast
  integration. Those are upstream responsibilities, currently handled by
  `mpaswf`.
- ESMPy weight generation is internal to the package; there is no NCL or SCRIP
  executable requirement.
- BFLOW, VBAL, UNBALANCE and HDIAG use file names declared in
  `bflow.products`.
- VBAL and HDIAG render YAML from the scientific control contract instead of
  hard-coded tutorial names.
- UNBALANCE is an explicit stage because the public toolbox path does not expose
  a reliable disk-written `samplesUnbalanced` contract.
- NICAS local reads in SO/DIRAC split 3D and 2D groups to avoid `nl0`
  dimensionality errors.
- SO and DIRAC use aliases for JEDI/SABER/BUMP product reads but keep MPAS
  stream files MPAS-native.
- DIRAC is represented as a first-class stage and produces `mpas.dirac.nc`.
- PLOTS is represented as a local post-processing stage after DIRAC.

## Maintained invariants

Do not change these without a new end-to-end validation:

1. one public command: `mpas-bmatrix`;
2. explicit UNBALANCE before HDIAG;
3. canonical `in code` names plus NetCDF `in file` aliases;
4. split NICAS read grids for 3D controls and 2D surface pressure;
5. MPAS-native output streams for SO/DIRAC;
6. DIRAC contract based on full `dirLats`/`dirLons` plus singular selectors;
7. persistent audits outside `/tmp`;
8. CDF5 validation for final NetCDF products.
