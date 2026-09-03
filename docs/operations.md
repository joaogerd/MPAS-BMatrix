# Operations, validation and troubleshooting

## Stage validation

Each production stage has a `validate` path through the public CLI:

```bash
mpas-bmatrix validate --config "$CONFIG" --bflow-workspace "$BFLOW" --stage <stage>
```

Production stages:

```text
bflow
vbal
hdiag
nicas
so
dirac
plots
```

The build orchestration validates each completed stage before launching the next
dependent stage. `unbalance_core` is retained only for migration A/B testing and
is not accepted as a production `--stage` value.

## Provenance

Prepared or completed stages write `stage-manifest.json` where available. These
manifests are the operational provenance record. Keep audit material under a
durable work directory rather than `/tmp`.

## VBAL -> HDIAG operational check

The production HDIAG workspace should contain links equivalent to:

```text
samples -> <VBAL workspace>/samples
vbal    -> <VBAL workspace>/VBAL
```

The generated `run_hdiag.yaml` must read `../samples/...` and contain a
`BUMP_VerticalBalance` outer block with `read local sampling: true` and
`read vertical balance: true` before BUMP_NICAS calibration.

No `samplesUnbalanced` files are expected in a production run.

## Common failures

### Missing VBAL products while preparing HDIAG

Cause: HDIAG now depends directly on a completed VBAL workspace.

Check that `mpas_vbal.nc`, `mpas_sampling.nc`, local VBAL/sampling files and the
staged `samples/PTB_f48mf24_*.nc` exist before preparing HDIAG.

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
grid. Keep `BUMP_NICAS.read.grids` split into 3D and 2D groups.

### `Jb is NaN`

Past cause: missing or incomplete aliases and mixed old/new variable names in
the B application YAML. Keep canonical control names in application slots and
aliases for NetCDF product reads.

### `signal 11` after `CostFunction::addIncrement`

Ensure `background.state variables` includes the canonical analysis output
variables, especially `water_vapor_mixing_ratio_wrt_moist_air`.

### `ERROR: Requested field eastward_wind not available`

Cause: canonical JEDI names were written to an MPAS stream list. Reuse compatible
MPAS-native stream files instead.

## A/B migration validation

For this branch, compare the retained materialized reference path with the
production in-memory path before merge:

```bash
python scripts/compare_hdiag_ab.py \
  /path/to/reference-hdiag \
  /path/to/in-memory-hdiag \
  --output hdiag-ab-comparison.csv
```

See [`in-memory-vbal-hdiag.md`](in-memory-vbal-hdiag.md) for the complete
HDIAG/NICAS/DIRAC/SO acceptance procedure.

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

For the in-memory VBAL migration, the numerical A/B and JACI end-to-end checks
are additional mandatory gates.
