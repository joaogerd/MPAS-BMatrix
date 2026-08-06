# JACI quick start

This page gives the shortest supported command sequence for the global
`x1.10242` case on JACI.

For explanations, read [`configuration.md`](configuration.md) and
[`user-guide.md`](user-guide.md).

## 1. Clone the repositories

```bash
export PROJECT_ROOT=/path/to/projects
export WORK_ROOT=/path/to/work/MPAS-BMatrix

mkdir -p "$PROJECT_ROOT" "$WORK_ROOT"
cd "$PROJECT_ROOT"

git clone https://github.com/joaogerd/MPAS-BMatrix.git
git clone https://github.com/joaogerd/mpaswf.git

export BMATRIX_ROOT="$PROJECT_ROOT/MPAS-BMatrix"
export MPASWF_ROOT="$PROJECT_ROOT/mpaswf"
```

## 2. Export the JACI/x1.10242 paths

```bash
export MONAN_JEDI_SOURCE=/path/to/projects/MONAN-JEDI
export MONAN_JEDI_INSTALL=/path/to/install/monan-jedi-mpas
export MONAN_JEDI_UNBALANCE_EXE=/path/to/mpasjedi_unbalance_ensemble.x

export MPAS_MESH_ROOT=/path/to/mpas_meshes
export MPAS_JEDI_STATIC_ROOT=/path/to/validated/x1.10242/static-files

export STACK_ROOT=/path/to/spack-stack
```

## 3. Load the environment and install

```bash
cd "$BMATRIX_ROOT"
source scripts/load_jaci_env.sh

python -m pip install --no-deps -e "$MPASWF_ROOT"
python -m pip install -e "$BMATRIX_ROOT"
```

Optional plotting/testing extras:

```bash
python -m pip install -e "$BMATRIX_ROOT[diagnostics,dev]"
```

## 4. Validate the composed configuration

```bash
cd "$BMATRIX_ROOT"
export CONFIG=configs/jaci-x1.10242.yaml

PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix check-config \
  --config "$CONFIG"
```

Do not continue if any required value remains as `${VARIABLE}` or resolves to the
wrong mesh, installation, static directory, queue or work root.

## 5. Run from a `mpaswf` manifest

```bash
export MANIFEST=/path/to/mpaswf-work/products/mpas-forecast-manifest.tsv

test -s "$MANIFEST"
```

Dry-run:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage plots \
  --dry-run
```

Full run:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage plots \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean \
  --poll-seconds 30
```

## 6. Resume from an existing BFLOW workspace

```bash
export BFLOW="$WORK_ROOT/bmatrix/bflow_preprocessing/np128_<START_VALID>_<END_VALID>"

PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
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
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
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
  PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix validate \
    --config "$CONFIG" \
    --bflow-workspace "$BFLOW" \
    --stage "$stage" || break
done
```

List reusable final products:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix products \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW"
```

## 9. Development checks

```bash
cd "$BMATRIX_ROOT"
mkdir -p .pytest-tmp

TMPDIR="$BMATRIX_ROOT/.pytest-tmp" \
PYTHONPATH="src:${PYTHONPATH:-}" \
python -m pytest -p no:cacheprovider -q

python -m ruff check src/bmatrix tests

git diff --check
```
