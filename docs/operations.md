# Operations, validation and troubleshooting

## Stage validation

Each stage has a `validate` path through the public CLI:

```bash
mpas-bmatrix validate --config "$CONFIG" --bflow-workspace "$BFLOW" --stage <stage>
```

Stages:

```text
bflow
vbal
unbalance
hdiag
nicas
so
dirac
plots
```

The build orchestration validates each completed stage before launching the next
dependent stage.

## Provenance

Prepared or completed stages write `stage-manifest.json` where available. These
manifests are the operational provenance record and should be treated as more
reliable than ad hoc README files inside workspaces.

Record audits under a durable work directory, for example:

```bash
AUDIT_DIR="$WORK_ROOT/audits"
mkdir -p "$AUDIT_DIR"
```

Do not rely on `/tmp` for persistent reports because it may be inaccessible from
other login nodes and may be removed.

## Common failures

### `horizontal distance larger than universe radius`

Cause: HDIAG/BUMP sampling extent exceeds the default BUMP universe radius.

Check:

```text
(distance classes - 1) * distance class width
```

The validated configuration uses:

```yaml
distance classes: 10
distance class width: 1000000.0
```

### `wrong size for dimension nl0`

Cause: local NICAS groups with different vertical dimensionality are read as one
grid. The 2D `surface_pressure` group has `nl0 = 1`, while the 3D controls use
`nl0 = 55`.

Fix: keep `BUMP_NICAS.read.grids` split into 3D and 2D groups.

### `Jb is NaN`

Past cause: missing or incomplete aliases and mixed old/new variable names in
the B application YAML.

Fix: keep canonical control names in `active variables`,
`Control2Analysis.input variables` and `vertical balance.vbal`; keep aliases for
NetCDF product reads.

### `signal 11` after `CostFunction::addIncrement`

Past cause: `Control2Analysis.output variables` included canonical analysis
variables that were not present in the background/State.

Fix: ensure `background.state variables` includes the canonical analysis output
variables, especially:

```text
water_vapor_mixing_ratio_wrt_moist_air
```

This field may be copied from `spechum` or derived from `qv / (1 + qv)`.

### `ERROR: Requested field eastward_wind not available`

Cause: canonical JEDI names were written to an MPAS stream list.

Fix: do not write canonical names to `stream_list.atmosphere.analysis`. Reuse the
MPAS-native stream files from the compatible HDIAG/static setup.

## CDF5 checks

For products that must be CDF5:

```bash
ncdump -k <file.nc>
```

Expected:

```text
cdf5
```

## Product checks

List final reusable products:

```bash
mpas-bmatrix products --config "$CONFIG" --bflow-workspace "$BFLOW"
```

Inspect important outputs:

```bash
SO=/path/to/so/workspace
DIRAC=/path/to/dirac/workspace

ncdump -h "$SO/an.YYYY-MM-DD_HH.MM.SS.nc" | \
  egrep 'uReconstructZonal|uReconstructMeridional|theta|qv|surface_pressure'

ncdump -k "$DIRAC/mpas.dirac.nc"
```

## Merge gate

Before merging:

```bash
cd "$BMATRIX_ROOT"
mkdir -p .pytest-tmp

TMPDIR="$BMATRIX_ROOT/.pytest-tmp" \
PYTHONPATH="src:${PYTHONPATH:-}" \
python -m pytest -p no:cacheprovider -q

python -m ruff check src/bmatrix tests

git diff --check
```
