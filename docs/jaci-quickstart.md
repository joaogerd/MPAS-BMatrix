# JACI quick start

Shortest supported sequence for the global `x1.10242` case.

## 1. Create the Python environment and install

Follow [install-jaci.md](install-jaci.md). The guide creates a Conda environment
with Python 3.11 and installs both repositories. Confirm:

```bash
conda activate monan-jedi-bmatrix
mpaswf --help
mpas-bmatrix --help
python -c "import sys, numpy; print(sys.executable); print(numpy.__file__)"
```

Both printed paths must belong to the active Conda environment. A Conda Python
must not import NumPy from a `spack-stack/.../py-numpy-.../python3.11` path.

## 2. Export the runtime/case roots

MONAN-JEDI provides one public runtime installation for the whole workflow:

```bash
export MONAN_JEDI_INSTALL_ROOT="/p/projetos/monan_das/$USER/build/monan-jedi"
export STACK_ROOT="/path/to/validated/spack-stack"
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
mpas-bmatrix check-config --config "$CONFIG"
```

Confirm that the resolved configuration points to the public MONAN-JEDI install
and not to a source/work tree.

## 4. Run from a `mpaswf` manifest

```bash
# This is the standard location written by the MPASWF JACI configuration.
# $USER is replaced automatically by the current JACI login name.
export MANIFEST="/p/projetos/monan_das/$USER/work/mpaswf/products/mpas-forecast-manifest.tsv"
test -s "$MANIFEST" || {
  echo "Forecast-pair file not found: $MANIFEST"
  echo "Run the MPASWF manifest phase before starting MPAS-BMatrix."
  return 1 2>/dev/null || exit 1
}

mpas-bmatrix build \
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
mpas-bmatrix build \
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

mpas-bmatrix build \
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
python -m pytest -p no:cacheprovider -q

python -m ruff check src/bmatrix tests
git diff --check
```

See [configuration.md](configuration.md) for the ownership of each setting and
[in-memory-vbal-hdiag.md](in-memory-vbal-hdiag.md) for the migration A/B check.
