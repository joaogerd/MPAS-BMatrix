# In-memory VBAL transform in HDIAG

## Status

The production static-B workflow uses the current NCAR/MPAS-JEDI pattern:

```text
BFLOW -> VBAL -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

VBAL calibrates the vertical-balance coefficients and sampling products. HDIAG
then rereads the original NMC perturbation samples and applies the inverse
`BUMP_VerticalBalance` transform in memory as a SABER outer block before the
BUMP_NICAS diagnostics are calibrated.

The normal workflow therefore does **not** materialize
`samplesUnbalanced/PTB_f48mf24_*.nc`.

## Scientific equivalence

The previous implementation used an explicit intermediate stage:

```text
x_i -> K2^-1 x_i -> write samplesUnbalanced -> HDIAG
```

The current implementation evaluates the same transform inside HDIAG:

```text
x_i -> [K2^-1 inside SABER outer block] -> HDIAG
```

The intended scientific quantity passed to HDIAG is unchanged. The difference
is only whether the transformed members are written to and reread from disk.

## Legacy implementation

`src/bmatrix/unbalance_core/` is retained temporarily for controlled regression
comparisons. It is not included in `bmatrix.pipeline.STAGES` and is not invoked
by `mpas-bmatrix build`.

The legacy path requires the MONAN-JEDI `mpasjedi_unbalance_ensemble.x`
executable. The production path does not.

## A/B validation on JACI

Use the same BFLOW workspace, VBAL products, NMC members, executable build, MPI
layout and scientific configuration for both paths.

### A. Materialized reference

Run the retained legacy sequence:

```text
VBAL
  -> UNBALANCE (K2^-1 and NetCDF output)
  -> HDIAG configured to read samplesUnbalanced
```

Preserve the resulting:

```text
mpas.stddev.nc
mpas.cor_rh.nc
mpas.cor_rv.nc
```

### B. In-memory production path

Run the branch production sequence:

```text
VBAL
  -> HDIAG reading samples/PTB_f48mf24_*.nc
       with BUMP_VerticalBalance as outer block
```

Preserve the same three HDIAG products.

### Automated HDIAG comparison

The branch contains `scripts/compare_hdiag_ab.py`. It recursively reads NetCDF
groups and compares every common numeric variable in `mpas.stddev.nc`,
`mpas.cor_rh.nc` and `mpas.cor_rv.nc`.

Example:

```bash
python scripts/compare_hdiag_ab.py \
  /path/to/materialized-reference-hdiag \
  /path/to/in-memory-hdiag \
  --rtol 1e-6 \
  --atol 1e-8 \
  --output hdiag-ab-comparison.csv
```

The command exits with zero only when the required products/variables match and
all compared values satisfy the selected tolerance. The CSV records:

- maximum absolute difference;
- RMS difference;
- maximum relative difference where the reference magnitude is significant;
- finite-value mismatch count;
- NaN mismatch count;
- Inf mismatch count;
- pass/fail status for each variable.

The default `rtol=1e-6` and `atol=1e-8` are initial regression tolerances, not a
scientific conclusion. Record the observed differences and tighten or justify
the final tolerance from the A/B results.

### Downstream comparison

After HDIAG equivalence is established, run NICAS from both HDIAG outputs and
compare the resulting BUMP/NICAS products. Finally run the same DIRAC and
single-observation tests with both matrices and compare the resulting responses.

## Acceptance criteria

The migration can replace the legacy path definitively when:

1. VBAL products are identical because both paths share the same calibration;
2. HDIAG `stddev`, `cor_rh` and `cor_rv` products are numerically equivalent
   within a documented floating-point tolerance;
3. NICAS products and DIRAC responses are consistent within the same scientific
   tolerance;
4. the single-observation 3D-Var validation remains successful;
5. the full production workflow completes without requiring
   `mpasjedi_unbalance_ensemble.x` or `samplesUnbalanced`.

After these checks, `unbalance_core` and its configuration can be removed in a
separate cleanup change.
