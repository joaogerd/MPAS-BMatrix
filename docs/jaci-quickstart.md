# JACI quick start

Shortest supported sequence for the global `x1.10242` case.

## 1. Clone/install

```bash
export PROJECT_ROOT=/path/to/projects
export WORK_ROOT=/path/to/work/MPAS-BMatrix
mkdir -p "$PROJECT_ROOT" "$WORK_ROOT"
cd "$PROJECT_ROOT"

git clone https://github.com/joaogerd/MPAS-BMatrix.git
git clone https://github.com/joaogerd/mpaswf.git

export BMATRIX_ROOT="$PROJECT_ROOT/MPAS-BMatrix"
export MPASWF_ROOT="$PROJECT_ROOT/mpaswf"

python -m pip install --no-deps -e "$MPASWF_ROOT"
python -m pip install -e "$BMATRIX_ROOT"
```

## 2. Export the runtime/case roots

MONAN-JEDI provides one public runtime installation for the whole workflow:

```bash
export MONAN_JEDI_INSTALL_ROOT=/p/projetos/monan_das/$USER/build/monan-jedi
export MPAS_MESH_ROOT=/path/to/mpas_meshes
export MPAS_JEDI_STATIC_ROOT=/path/to/validated/x1.10242/static-files
export STACK_ROOT=/path/to/spack-stack
```

You do **not** need to export `MONAN_JEDI_SOURCE` or
`MONAN_JEDI_UNBALANCE_EXE` for the production configuration.

Compatibility note: old scripts exporting `MONAN_JEDI_INSTALL` still work when
`MONAN_JEDI_INSTALL_ROOT` is absent.

## 3. Load and validate

```bash
cd "$BMATRIX_ROOT"
source scripts/load_jaci_env.sh

export CONFIG=configs/jaci-x1.10242.yaml
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix check-config --config "$CONFIG"
```

Confirm that the resolved configuration points to the public MONAN-JEDI install
and not to a source/work tree.

## 4. Run from a `mpaswf` manifest

```bash
export MANIFEST=/path/to/mpaswf-work/products/mpas-forecast-manifest.tsv
test -s "$MANIFEST"

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

Dry-run first when changing a campaign:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --manifest "$MANIFEST" \
  --from-stage bflow \
  --to-stage plots \
  --dry-run
```

The plan must follow:

```text
bflow -> vbal -> hdiag -> nicas -> so -> dirac -> plots
```

## 5. Resume from an existing BFLOW workspace

```bash
export BFLOW="$WORK_ROOT/bmatrix/bflow_preprocessing/np128_<START_VALID>_<END_VALID>"

PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage vbal \
  --to-stage plots \
  --clean \
  --poll-seconds 30
```

Valid production stages:

```text
bflow, vbal, hdiag, nicas, so, dirac, plots
```

HDIAG reads the original `samples/PTB_f48mf24_*.nc` and applies inverse VBAL in
memory. `samplesUnbalanced` and the explicit UNBALANCE executable are not part of
the production run.

## 6. Development checks

```bash
cd "$BMATRIX_ROOT"
mkdir -p .pytest-tmp

TMPDIR="$BMATRIX_ROOT/.pytest-tmp" \
PYTHONPATH="src:${PYTHONPATH:-}" \
python -m pytest -p no:cacheprovider -q

python -m ruff check src/bmatrix tests
git diff --check
```

See [configuration.md](configuration.md) for the ownership of each setting and
[in-memory-vbal-hdiag.md](in-memory-vbal-hdiag.md) for the migration A/B check.
