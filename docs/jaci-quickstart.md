# JACI quick start

This page gives a generic command sequence for the global `x1.10242` case on
JACI. Replace only the exported roots for your account/project.

## 1. Clone the required repositories

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

Install the Python packages in the active environment:

```bash
python -m pip install --no-deps -e "$MPASWF_ROOT"
python -m pip install -e "$BMATRIX_ROOT"
```

## 2. Load the MPAS-JEDI environment

The repository includes a path-generic JACI loader. Set `STACK_ROOT` to the root
of the spack-stack environment available on your system.

```bash
cd "$BMATRIX_ROOT"
export STACK_ROOT=/path/to/spack-stack
source scripts/load_jaci_env.sh
```

## 3. Set common inputs

For an existing BFLOW workspace:

```bash
CONFIG=configs/jaci-x1.10242.yaml
BFLOW="$WORK_ROOT/bmatrix/bflow_preprocessing/np128_<START_VALID>_<END_VALID>"
```

For a fresh run from `mpaswf` pairs:

```bash
MANIFEST=/path/to/mpaswf-work/products/mpas-forecast-manifest.tsv
```

## 4. Check the resolved configuration

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix check-config \
  --config "$CONFIG"
```

## 5. Build from a `mpaswf` manifest

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage plots \
  --clean \
  --poll-seconds 30
```

## 6. Run selected stages from an existing BFLOW workspace

Only UNBALANCE:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage unbalance \
  --to-stage unbalance \
  --clean \
  --poll-seconds 10
```

UNBALANCE through HDIAG:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage unbalance \
  --to-stage hdiag \
  --clean \
  --poll-seconds 10
```

NICAS only after HDIAG is valid:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage nicas \
  --to-stage nicas \
  --clean \
  --poll-seconds 10
```

SO only after NICAS is valid:

```bash
AUDIT_DIR="$WORK_ROOT/audits"
mkdir -p "$AUDIT_DIR"

PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage so \
  --to-stage so \
  --clean \
  --poll-seconds 10 \
  2>&1 | tee "$AUDIT_DIR/so_latest.log"
```

DIRAC only after SO and NICAS are valid:

```bash
AUDIT_DIR="$WORK_ROOT/audits"
mkdir -p "$AUDIT_DIR"

PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage dirac \
  --to-stage dirac \
  --clean \
  --poll-seconds 10 \
  2>&1 | tee "$AUDIT_DIR/dirac_latest.log"
```

Full workflow through DIRAC:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --clean \
  --poll-seconds 10
```

Full workflow through plots:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --to-stage plots \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean \
  --poll-seconds 10
```

## 7. Validate completed products

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix validate \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --stage so

PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix validate \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --stage dirac
```

## 8. Generate plots only

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix plots \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --plot-level 30 \
  --plot-dpi 150 \
  --clean
```

## 9. Development checks

Always run:

```bash
cd "$BMATRIX_ROOT"
mkdir -p .pytest-tmp

TMPDIR="$BMATRIX_ROOT/.pytest-tmp" \
PYTHONPATH="src:${PYTHONPATH:-}" \
python -m pytest -p no:cacheprovider -q

python -m ruff check src/bmatrix tests

git diff --check
```

Avoid writing persistent audit files to `/tmp`. Use a durable project work area,
for example:

```text
$WORK_ROOT/audits/
```
