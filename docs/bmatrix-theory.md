# B-matrix theory and stage meaning

This document summarizes the scientific meaning of the static MPAS-JEDI/SABER
B-matrix workflow implemented in this repository.

## What the B-matrix represents

In variational data assimilation, the background-error covariance matrix `B`
controls how increments are distributed when observations modify the background
state. Conceptually, `B` determines:

```text
- the amplitude of expected background errors;
- how information spreads horizontally;
- how information spreads vertically;
- how increments in one variable project onto other variables;
- how a control-space increment becomes an analysis-space increment.
```

For a global MPAS-JEDI/SABER application, `B` is represented by a sequence of
operators and NetCDF products rather than one dense matrix:

```text
B ≈ C2A · VBAL · StdDev · NICAS · StdDev · VBALᵀ · C2Aᵀ
```

where `NICAS` represents spatial correlation, `StdDev` sets error amplitude,
`VBAL` represents vertical/multivariate balance, and `C2A` is the
`Control2Analysis` variable change.

## Stage overview

The production order is:

```text
mpaswf -> BFLOW -> VBAL -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

`mpaswf` is upstream and external. This repository starts at `BFLOW`.

| Stage | Scientific role | Main products |
| --- | --- | --- |
| `mpaswf` | Generates same-valid-time f024/f048 MPAS forecasts for the NMC method. | forecast-pair manifest and MPAS states. |
| `BFLOW` | Converts NMC forecast pairs into control-space full fields and perturbations. | `FULL_f24.nc`, `FULL_f48.nc`, `PTB_f48mf24.nc`. |
| `VBAL` | Estimates vertical/multivariate balance relationships. | `mpas_vbal.nc`, `mpas_sampling.nc`, local products. |
| `HDIAG` | Applies inverse VBAL in memory and computes standard deviations and horizontal/vertical correlation scales. | `mpas.stddev.nc`, `mpas.cor_rh.nc`, `mpas.cor_rv.nc`. |
| `NICAS` | Builds the spatial correlation/localization operator using HDIAG scales. | `mpas_nicas.nc`, local products and diagnostics. |
| `SO` | Runs a single-observation variational test of the complete B. | `obsout_SO_*.h5`, `an.*.nc`, logs. |
| `DIRAC` | Applies an impulse to diagnose the response of the complete B. | `mpas.dirac.nc`. |
| `PLOTS` | Produces visual diagnostics from completed products. | `summary.csv`, figures. |

## Control space and analysis space

The B-matrix is calibrated in control space:

| Canonical code name | NetCDF/file name | Role |
| --- | --- | --- |
| `air_horizontal_streamfunction` | `stream_function` | Rotational wind control. |
| `air_horizontal_velocity_potential` | `velocity_potential` | Divergent wind control. |
| `air_temperature` | `temperature` | Temperature control. |
| `water_vapor_mixing_ratio_wrt_moist_air` | `spechum` | Moisture control. |
| `air_pressure_at_surface` | `surface_pressure` | Surface-pressure control. |

SABER/OOPS uses canonical names internally. Explicit aliases bridge those names
to names stored in NetCDF products.

After `Control2Analysis`, the analysis variables are:

```text
eastward_wind
northward_wind
air_temperature
water_vapor_mixing_ratio_wrt_moist_air
air_pressure_at_surface
```

MPAS stream output remains MPAS-native.

## BFLOW: NMC perturbations in control space

For valid time `T`, the NMC perturbation is:

```text
f048(T), initialized at T - 48 h
minus
f024(T), initialized at T - 24 h
```

`mpaswf` produces the forecast pairs. BFLOW prepares the full fields,
`PTB_f48mf24.nc`, derived controls, and any required regridding products.

## VBAL: balanced relationships

`VBAL` calibrates `BUMP_VerticalBalance`. In the current configuration the main
balance source is streamfunction:

```text
velocity_potential  <- stream_function
temperature         <- stream_function
surface_pressure    <- stream_function
```

`mpas_vbal.nc` stores the balance coefficients. `mpas_sampling.nc` and local
sampling products store the BUMP sampling information. VBAL is a calibration
stage; it does not need to write a transformed ensemble.

## Inverse balance transform before HDIAG

HDIAG must estimate amplitude and correlation scales from perturbations in the
unbalanced control space. The scientific operation is the inverse balance
transform `K2^-1`.

The previous implementation materialized that result:

```text
centered NMC sample
  -> K2^-1
  -> samplesUnbalanced/*.nc
  -> HDIAG
```

The production implementation performs the same operation inside the SABER
chain:

```text
centered NMC sample
  -> BUMP_VerticalBalance outer block
  -> inverse transform in memory
  -> BUMP_NICAS HDIAG calibration
```

Thus the scientific quantity entering HDIAG is unchanged; only the unnecessary
write/read of transformed members is removed. This also avoids dependence on the
removed `background error.output ensemble` behavior.

The retained `unbalance_core` represents the former materialized path solely for
A/B regression validation. See
[`in-memory-vbal-hdiag.md`](in-memory-vbal-hdiag.md).

## HDIAG: amplitude and length-scale diagnostics

HDIAG produces:

```text
mpas.stddev.nc  -> standard deviation / background-error amplitude
mpas.cor_rh.nc  -> horizontal correlation scale
mpas.cor_rv.nc  -> vertical correlation scale
```

The standard-deviation product feeds `StdDev`; the scale products feed NICAS.
The original NMC samples are read from `samples/`, transformed by inverse VBAL in
memory, and then consumed by BUMP_NICAS.

## NICAS: spatial correlation/localization

NICAS uses the HDIAG horizontal and vertical scales to construct the spatial
correlation/localization operator. Reusable and diagnostic products include:

```text
merge/mpas_nicas.nc
merge/mpas_nicas_local_*
merge/mpas_nicas_grids_local_*
merge/mpas.nicas_norm.nc
merge/mpas.dirac_nicas.nc
```

The NICAS-only DIRAC diagnostic is distinct from the complete-B
`DIRAC/mpas.dirac.nc`.

## SO: single-observation variational validation

SO validates the complete B in `mpasjedi_variational.x` using:

```text
BUMP_NICAS + StdDev + BUMP_VerticalBalance + Control2Analysis
```

A successful run demonstrates compatibility of the B products, aliases,
background fields, observation configuration and variable change.

## DIRAC: complete-B impulse response

DIRAC applies a control-space impulse through the complete B:

```text
BUMP_NICAS + StdDev + BUMP_VerticalBalance + Control2Analysis
```

and writes `mpas.dirac.nc` for scientific inspection of the response.

## PLOTS: visual diagnostics

PLOTS reads completed products and generates figures and summaries without
modifying the B products.

## Product dependency map

```text
mpaswf manifest
  -> BFLOW/FULL_f24.nc, FULL_f48.nc, PTB_f48mf24.nc
      -> VBAL/mpas_vbal.nc, mpas_sampling.nc
          -> HDIAG reads original samples and applies K2^-1 in memory
              -> mpas.stddev.nc, mpas.cor_rh.nc, mpas.cor_rv.nc
                  -> NICAS/merge/mpas_nicas.nc
                      -> SO validation
                      -> DIRAC/mpas.dirac.nc
                          -> PLOTS
```

The minimal reusable B product set is:

```text
VBAL/mpas_vbal.nc
VBAL/mpas_sampling.nc
HDIAG/mpas.stddev.nc
NICAS/merge/mpas_nicas.nc
```

Preserve the additional diagnostics for provenance and scientific inspection.
