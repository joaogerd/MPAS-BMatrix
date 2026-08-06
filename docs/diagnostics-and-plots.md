# Diagnostics and plots

The `plots` stage is local post-processing. It does not submit PBS jobs and does
not modify scientific NetCDF products.

## Command

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix plots \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean
```

## Output layout

The default output path is derived from the BFLOW workspace:

```text
${work_root}/bmatrix/plots/<RUN_ID>/
```

Expected contents:

```text
summary.csv
README.md

01_stddev/
02_corr_horizontal/
03_corr_vertical/
04_vbal/
05_dirac/
06_spatial_fields/
```

## Figure groups

### 01_stddev

Latitude-level and/or spatial views of standard deviations from:

```text
HDIAG/mpas.stddev.nc
```

Use these figures to check the amplitude of each control variable.

### 02_corr_horizontal

Diagnostics from:

```text
HDIAG/mpas.cor_rh.nc
```

Use these figures to inspect horizontal correlation scales. Watch for
unphysical discontinuities, zero fields, or scales inconsistent with the BUMP
sampling configuration.

### 03_corr_vertical

Diagnostics from:

```text
HDIAG/mpas.cor_rv.nc
```

Use these figures to inspect vertical correlation scales.

### 04_vbal

VBAL diagnostics from:

```text
VBAL/mpas_vbal.nc
```

Use these to inspect the explained variance and balance relationships between
streamfunction and the balanced variables.

### 05_dirac

Local complete-B impulse responses from:

```text
DIRAC/mpas.dirac.nc
```

These are the main diagnostic figures for spatial response. When Cartopy is
available, coastlines and borders are drawn as map context. When Cartopy is not
available, the figure falls back to plain Matplotlib axes.

### 06_spatial_fields

Global spatial maps for broad diagnostics, especially:

```text
stddev
cor_rh
cor_rv
nicas_norm
```

These figures should not duplicate the local DIRAC response plots.

## Style conventions

The maintained plotting style follows a publication-oriented layout:

- sans-serif font family with editable text in vector outputs;
- bold, left-aligned titles close to the plot area;
- clean white background;
- subtle dotted grid lines;
- no framed legends unless needed;
- outward ticks;
- sequential palettes for positive-only magnitudes;
- diverging palettes for fields with a meaningful zero;
- colorblind-conscious palettes and no rainbow/jet colormap.

## Practical checks

After generating plots, verify that:

1. the figure directories are present;
2. `summary.csv` exists;
3. spatial maps have titles and colorbar labels;
4. maps with geographic coordinates include coastlines when Cartopy is installed;
5. near-zero fields are not overinterpreted as meaningful B responses;
6. DIRAC responses are inspected locally, not only on global maps.
