# B-matrix theory and stage meaning

This document summarizes the scientific meaning of the static MPAS-JEDI/SABER
B-matrix workflow implemented in this repository. It consolidates the conceptual
material from the original `mpas-bmatrix-global` documentation and updates the
stage order to include the explicit `UNBALANCE` stage used by the current
pipeline.

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

For a global MPAS-JEDI/SABER application, `B` is not built or stored as one dense
matrix. It is represented by a sequence of operators and NetCDF products:

```text
B ≈ C2A · VBAL · StdDev · NICAS · StdDev · VBALᵀ · C2Aᵀ
```

where:

| Operator | Meaning |
| --- | --- |
| `NICAS` | Spatial correlation/localization operator. |
| `StdDev` | Standard-deviation operator that sets error amplitude. |
| `VBAL` | Vertical and multivariate balance operator. |
| `C2A` | `Control2Analysis` linear variable change from control variables to analysis variables. |

The practical product set is therefore a collection of BUMP/SABER files, not one
single covariance file.

## Stage overview

The current operational order is:

```text
mpaswf -> BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

`mpaswf` is upstream and external to this package. It generates MPAS f024/f048
forecasts and the forecast-pair manifest. This repository starts at `BFLOW`.

| Stage | Scientific role | Main products |
| --- | --- | --- |
| `mpaswf` | Generates same-valid-time f024/f048 MPAS forecasts for the NMC method. | `mpas-forecast-manifest.tsv`, MPAS `da_state`/`restart` products. |
| `BFLOW` | Converts the NMC forecast pairs into control-space full fields and perturbations. | `FULL_f24.nc`, `FULL_f48.nc`, `PTB_f48mf24.nc`, `manifest.tsv`. |
| `VBAL` | Estimates vertical/multivariate balance relationships. | `mpas_vbal.nc`, `mpas_sampling.nc`, local VBAL/sampling files. |
| `UNBALANCE` | Applies the inverse balance transform to write unbalanced training members. | `samplesUnbalanced/PTB_f48mf24_*.nc`. |
| `HDIAG` | Computes standard deviations and horizontal/vertical correlation scales from the unbalanced samples. | `mpas.stddev.nc`, `mpas.cor_rh.nc`, `mpas.cor_rv.nc`. |
| `NICAS` | Builds the spatial correlation/localization operator using HDIAG scales. | `mpas_nicas.nc`, local NICAS files, `mpas.nicas_norm.nc`, `mpas.dirac_nicas.nc`. |
| `SO` | Runs a single-observation variational test to validate that the complete B can be read and applied. | `obsout_SO_*.h5`, `an.*.nc`, run logs. |
| `DIRAC` | Applies an impulse to diagnose the response of the complete B directly. | `mpas.dirac.nc`. |
| `PLOTS` | Produces visual diagnostics from completed products. | `summary.csv`, diagnostic figures. |

## Control space and analysis space

The B-matrix is calibrated in control space. In the current contract, the control
variables are:

| Canonical code name | NetCDF/file name | Role |
| --- | --- | --- |
| `air_horizontal_streamfunction` | `stream_function` | Rotational wind control. |
| `air_horizontal_velocity_potential` | `velocity_potential` | Divergent wind control. |
| `air_temperature` | `temperature` | Temperature control. |
| `water_vapor_mixing_ratio_wrt_moist_air` | `spechum` | Moisture control. |
| `air_pressure_at_surface` | `surface_pressure` | Surface-pressure control. |

SABER/OOPS uses the canonical names internally. The NetCDF products may contain
historical/tutorial names. The `in code`/`in file` aliases bridge those names for
JEDI/SABER/BUMP product reads.

The analysis-space variables after `Control2Analysis` are:

```text
eastward_wind
northward_wind
air_temperature
water_vapor_mixing_ratio_wrt_moist_air
air_pressure_at_surface
```

These canonical analysis names must not be written directly to MPAS stream lists.
MPAS streams are validated against MPAS Registry names and therefore remain
MPAS-native.

## BFLOW: NMC perturbations in control space

The NMC method uses pairs of forecasts valid at the same time but initialized at
different times. For valid time `T`:

```text
older forecast: f048 initialized at T - 48 h
newer forecast: f024 initialized at T - 24 h
perturbation:   f048(T) - f024(T)
```

`mpaswf` produces the MPAS forecast products and manifest. `BFLOW` then performs
the B-matrix-specific preparation:

```text
MPAS forecast pairs
  -> full fields FULL_f48.nc and FULL_f24.nc
  -> perturbation PTB_f48mf24.nc
  -> derived controls such as stream_function, velocity_potential, temperature and spechum
  -> optional MPAS <-> regular-latlon ESMF weights
```

BFLOW is the first stage owned by this repository.

## VBAL: balanced relationships

`VBAL` calibrates the `BUMP_VerticalBalance` block. It estimates how part of one
control variable can be statistically explained by another. In the current
configuration, the key balance source is streamfunction:

```text
velocity_potential  <- stream_function
temperature         <- stream_function
surface_pressure    <- stream_function
```

The output `mpas_vbal.nc` stores the balance coefficients. `mpas_sampling.nc` and
local sampling products describe the sampling information used by BUMP. These
files are needed later by `SO`, `DIRAC`, and any application of the complete B.

## UNBALANCE: explicit K2 inverse application

The explicit `UNBALANCE` stage is the main correction relative to older
stage-only descriptions of the workflow.

The tutorial-style theoretical flow assumes that the samples used by HDIAG are
already in the unbalanced control space. In practice, the public toolbox path
used for VBAL calibration does not provide a reliable final disk-written contract
for those members when using iterative ensemble loading.

Therefore this repository keeps the step explicit:

```text
VBAL calibrates K2
UNBALANCE applies K2^-1 to centered PTB members
HDIAG reads samplesUnbalanced only
```

The resulting members are:

```text
samplesUnbalanced/PTB_f48mf24_001.nc
samplesUnbalanced/PTB_f48mf24_002.nc
samplesUnbalanced/PTB_f48mf24_003.nc
samplesUnbalanced/PTB_f48mf24_004.nc
...
```

These files are not raw perturbations. They are centered members after removal of
the balance component represented by `K2`.

## HDIAG: amplitude and length-scale diagnostics

`HDIAG` computes the BUMP diagnostics used by later stages:

```text
mpas.stddev.nc  -> standard deviation / amplitude of background error
mpas.cor_rh.nc  -> horizontal correlation scale
mpas.cor_rv.nc  -> vertical correlation scale
```

The standard deviation product is used by the `StdDev` block. The horizontal and
vertical scale products are used by `NICAS` to build the spatial correlation
operator.

The validated workflow reads unbalanced members from `samplesUnbalanced`, not raw
BFLOW PTBs.

## NICAS: spatial correlation/localization

`NICAS` constructs the spatial correlation/localization part of `B`. It uses the
horizontal and vertical correlation scales diagnosed by HDIAG:

```text
HDIAG/mpas.cor_rh.nc -> horizontal scales
HDIAG/mpas.cor_rv.nc -> vertical scales
```

NICAS is computed for the control variables and then merged into a single product
set that can be read by later SABER configurations:

```text
merge/mpas_nicas.nc
merge/mpas_nicas_local_*
merge/mpas_nicas_grids_local_*
```

Two diagnostics are also preserved:

```text
merge/mpas.nicas_norm.nc
merge/mpas.dirac_nicas.nc
```

`mpas.dirac_nicas.nc` is a NICAS-only diagnostic. It is not the same as the
complete-B `DIRAC/mpas.dirac.nc` product.

## SO: single-observation variational validation

`SO` means single-observation test. It does not calibrate the B. It validates
that the complete B can be read and applied by `mpasjedi_variational.x` in a
small 3D-Var-style experiment with synthetic observations.

The B composition exercised by SO is:

```text
BUMP_NICAS + StdDev + BUMP_VerticalBalance + Control2Analysis
```

A successful SO run demonstrates that the B products, aliases, background fields,
observation operator configuration, and linear variable change are compatible in
a variational application.

The analysis file `an.*.nc` is MPAS-native output written through MPAS streams.
It should not be expected to contain the canonical JEDI/OOPS variable names.

## DIRAC: complete-B impulse response

`DIRAC` diagnoses the mathematical response of the complete B directly. It
applies an impulse in one control variable and writes the response generated by:

```text
BUMP_NICAS + StdDev + BUMP_VerticalBalance + Control2Analysis
```

The output is:

```text
mpas.dirac.nc
```

This is different from the NICAS-only internal diagnostic. `DIRAC/mpas.dirac.nc`
should be used to inspect how the full B spreads information across space,
vertical levels, and variables.

## PLOTS: visual diagnostics

`PLOTS` is a local diagnostic stage. It reads completed NetCDF products and writes
figures and summaries. It does not calibrate, modify, or validate scientific B
products by itself.

The stage is useful for quick inspection of:

```text
- standard deviation amplitudes;
- horizontal and vertical scales;
- VBAL balance diagnostics;
- NICAS normalization;
- complete-B DIRAC responses;
- global spatial fields.
```

## Product dependency map

```text
mpaswf manifest
  -> BFLOW/FULL_f24.nc, FULL_f48.nc, PTB_f48mf24.nc
      -> VBAL/mpas_vbal.nc, mpas_sampling.nc
          -> UNBALANCE/samplesUnbalanced/PTB_f48mf24_*.nc
              -> HDIAG/mpas.stddev.nc, mpas.cor_rh.nc, mpas.cor_rv.nc
                  -> NICAS/merge/mpas_nicas.nc
                      -> SO validation
                      -> DIRAC/mpas.dirac.nc
                          -> PLOTS
```

The minimal reusable B product set for later SABER applications is:

```text
VBAL/mpas_vbal.nc
VBAL/mpas_sampling.nc
HDIAG/mpas.stddev.nc
NICAS/merge/mpas_nicas.nc
```

The diagnostic products should also be preserved for provenance and scientific
inspection:

```text
HDIAG/mpas.cor_rh.nc
HDIAG/mpas.cor_rv.nc
NICAS/merge/mpas.nicas_norm.nc
NICAS/merge/mpas.dirac_nicas.nc
DIRAC/mpas.dirac.nc
SO/obsout_SO_*.h5
PLOTS/summary.csv
```
