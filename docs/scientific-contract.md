# Scientific contract

This document records the scientific and naming contracts that must be preserved
when maintaining the `main` branch.

## Control variables

The static B-matrix is calibrated in control space:

| Canonical code name | NetCDF/file name | Dimensionality |
| --- | --- | --- |
| `air_horizontal_streamfunction` | `stream_function` | 3D |
| `air_horizontal_velocity_potential` | `velocity_potential` | 3D |
| `air_temperature` | `temperature` | 3D |
| `water_vapor_mixing_ratio_wrt_moist_air` | `spechum` | 3D |
| `air_pressure_at_surface` | `surface_pressure` | 2D |

The canonical names are used by the current MPAS-JEDI/SABER/OOPS code. The file
names are the names present in the NetCDF products produced by BFLOW, VBAL,
UNBALANCE, HDIAG and NICAS.

## Aliases

SABER/BUMP reads use explicit aliases:

```yaml
- in code: air_temperature
  in file: temperature
```

Meaning:

- `in code`: name expected internally by MPAS-JEDI/SABER/OOPS;
- `in file`: name stored in the NetCDF B-matrix product.

This alias applies to JEDI/SABER/BUMP product reads. It does not apply to the
MPAS stream parser.

Keep aliases in:

```text
geometry.alias
BUMP_NICAS.read.io.alias
BUMP_VerticalBalance.read.io.alias
```

VBAL also needs compound aliases for pair groups inside `mpas_vbal.nc`, such as:

```yaml
- in code: air_horizontal_streamfunction-air_temperature
  in file: stream_function-temperature
```

## Analysis variables

The analysis increment after `Control2Analysis` is in physical/canonical
analysis variables:

```text
eastward_wind
northward_wind
air_temperature
water_vapor_mixing_ratio_wrt_moist_air
air_pressure_at_surface
```

The B blocks operate in control space first:

```text
BUMP_NICAS -> StdDev -> BUMP_VerticalBalance -> Control2Analysis
```

Do not mix analysis variables inside the SABER B blocks before
`Control2Analysis`.

## MPAS-native streams

MPAS streams accept MPAS Registry fields, not arbitrary JEDI canonical names.
Therefore do not write these names to `stream_list.atmosphere.analysis`:

```text
eastward_wind
northward_wind
air_temperature
water_vapor_mixing_ratio_wrt_moist_air
air_pressure_at_surface
```

The SO `an.*.nc` output should remain MPAS-native. Typical minimum fields are:

```text
uReconstructZonal
uReconstructMeridional
theta
qv
surface_pressure
```

The fact that a canonical OOPS increment changed does not guarantee that the
MPAS-native stream output will show a non-zero `an-bg` difference for those
native fields. Do not use native `an-bg = 0` as an automatic failure criterion.

## Two-dimensional controls

`surface_pressure` / `air_pressure_at_surface` is a 2D control. When it is read
together with 3D controls by BUMP, the configuration must state how the 2D field
relates to the 3D geometry. For VBAL, keep:

```yaml
model:
  nearest 3d level: bottom
```

For local NICAS reads in SO/DIRAC, keep `read.grids` split into separate 3D and
2D groups.

## UNBALANCE

The tutorial-style expectation is that HDIAG consumes unbalanced perturbations.
In this implementation, that contract is made explicit:

```text
VBAL estimates K2
UNBALANCE applies K2^-1
HDIAG reads samplesUnbalanced
```

Do not rely on `background error.output ensemble` in
`mpasjedi_error_covariance_toolbox.x` to write the final unbalanced ensemble
members when using iterative ensemble loading. The public and reproducible
contract in this repository is the explicit UNBALANCE stage.

## DIRAC

DIRAC is a complete-B response diagnostic. It must use the same B composition as
SO:

```text
BUMP_NICAS + StdDev + BUMP_VerticalBalance + Control2Analysis
```

The maintained contract is:

```text
dirLats / dirLons full lists
ildir singular selector
dirvar singular variable
```

The product is:

```text
DIRAC/mpas.dirac.nc
```

## Required B products

The minimal products consumed by later MPAS-JEDI/SABER use are:

```text
VBAL/mpas_vbal.nc
VBAL/mpas_sampling.nc
HDIAG/mpas.stddev.nc
NICAS/merge/mpas_nicas.nc
```

Additional diagnostics should be preserved:

```text
HDIAG/mpas.cor_rh.nc
HDIAG/mpas.cor_rv.nc
NICAS/merge/mpas.nicas_norm.nc
NICAS/merge/mpas.dirac_nicas.nc
DIRAC/mpas.dirac.nc
```
