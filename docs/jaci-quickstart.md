# JACI quick start

This page gives the shortest supported command sequence for the global
`x1.10242` case on JACI.

For explanations, read [`getting-started.md`](getting-started.md),
[`configuration.md`](configuration.md) and [`user-guide.md`](user-guide.md).

## 1. Clone and install

```bash
git clone https://github.com/joaogerd/MPAS-BMatrix.git
cd MPAS-BMatrix
python -m pip install -e .
```

If you also need to generate the upstream MPAS forecast pairs, install `mpaswf`
separately following its own documentation.

## 2. Configure the user workspace

```bash
mpas-bmatrix setup --site jaci
```

Default:

```text
/p/projetos/monan_das/<USER>/work/MPAS-BMatrix
```

Optional override:

```bash
mpas-bmatrix setup --site jaci --workspace /path/to/work/MPAS-BMatrix
```

## 3. Validate the environment and resources

```bash
mpas-bmatrix doctor
```

Do not continue until the command ends with:

```text
READY
```

See every resolved path and its role with:

```bash
mpas-bmatrix paths
```

## 4. Validate the composed configuration

```bash
mpas-bmatrix check-config --config configs/jaci-x1.10242.yaml
```

For the complete JSON mapping:

```bash
mpas-bmatrix check-config --config configs/jaci-x1.10242.yaml --json
```

## 5. Run from a `mpaswf` manifest

```bash
MANIFEST=/path/to/mpaswf-work/products/mpas-forecast-manifest.tsv
test -s "$MANIFEST"
```

Dry-run:

```bash
mpas-bmatrix build \
  --config configs/jaci-x1.10242.yaml \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage plots \
  --dry-run
```

Full run:

```bash
mpas-bmatrix build \
  --config configs/jaci-x1.10242.yaml \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage plots \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean \
  --poll-seconds 30
```

## 6. Resume from an existing BFLOW workspace

Use `mpas-bmatrix paths` and the deterministic workspace naming to locate the
existing run, then:

```bash
BFLOW=/path/to/bflow/workspace

mpas-bmatrix build \
  --config configs/jaci-x1.10242.yaml \
  --bflow-workspace "$BFLOW" \
  --from-stage vbal \
  --to-stage plots \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean \
  --poll-seconds 30
```

## 7. Run one stage

```bash
mpas-bmatrix build \
  --config configs/jaci-x1.10242.yaml \
  --bflow-workspace "$BFLOW" \
  --from-stage dirac \
  --to-stage dirac \
  --clean \
  --poll-seconds 10
```

Valid stages:

```text
bflow, vbal, unbalance, hdiag, nicas, so, dirac, plots
```

## 8. Validate products

```bash
for stage in bflow vbal unbalance hdiag nicas so dirac plots; do
  mpas-bmatrix validate \
    --config configs/jaci-x1.10242.yaml \
    --bflow-workspace "$BFLOW" \
    --stage "$stage" || break
done
```

List reusable final products:

```bash
mpas-bmatrix products \
  --config configs/jaci-x1.10242.yaml \
  --bflow-workspace "$BFLOW"
```

## 9. Advanced overrides

Normal users should not begin by exporting all installation paths. If automatic
discovery is not appropriate for a non-standard installation, explicit overrides
remain available and are documented in [`configuration.md`](configuration.md).
