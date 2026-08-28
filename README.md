# MPAS-BMatrix

`MPAS-BMatrix` is the INPE/MONAN workflow for building, validating and
diagnosing static MPAS-JEDI/SABER/BUMP background-error covariance products.

The public command is:

```bash
mpas-bmatrix
```

## Scope

The repository starts at the **BFLOW** boundary. Forecast production is owned by
[`mpaswf`](https://github.com/joaogerd/mpaswf):

```text
mpaswf -> BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

`mpaswf` owns GFS/WPS, MPAS initialization/forecast integration and the
forecast-pair manifest. `MPAS-BMatrix` owns the covariance pipeline from BFLOW
onward.

## Runtime software contract

MONAN-JEDI is the single producer of the MPAS/JEDI runtime used by both
`mpaswf` and `MPAS-BMatrix`.

For JACI, configure one public installation root:

```bash
export MONAN_JEDI_INSTALL_ROOT=/p/projetos/monan_das/$USER/build/monan-jedi
```

MPAS-BMatrix derives runtime files from it, including:

```text
$MONAN_JEDI_INSTALL_ROOT/bin/mpasjedi_error_covariance_toolbox.x
$MONAN_JEDI_INSTALL_ROOT/bin/mpasjedi_variational.x
$MONAN_JEDI_INSTALL_ROOT/bin/mpasjedi_unbalance_ensemble.x
$MONAN_JEDI_INSTALL_ROOT/share/MPAS/core_atmosphere
$MONAN_JEDI_INSTALL_ROOT/share/monan-jedi/mpas-jedi/namelists/geovars.yaml
$MONAN_JEDI_INSTALL_ROOT/share/monan-jedi/mpas-jedi/namelists/keptvars.yaml
```

The workflow no longer needs `MONAN_JEDI_SOURCE` or a separately configured
`MONAN_JEDI_UNBALANCE_EXE` in the normal runtime path.

For compatibility, the configuration loader still accepts the historical
`MONAN_JEDI_INSTALL` environment variable when `MONAN_JEDI_INSTALL_ROOT` is not
set.

## Quick start

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

Set the runtime and case inputs:

```bash
export MONAN_JEDI_INSTALL_ROOT=/p/projetos/monan_das/$USER/build/monan-jedi
export MPAS_MESH_ROOT=/path/to/mpas_meshes
export MPAS_JEDI_STATIC_ROOT=/path/to/validated/x1.10242/static-files
export STACK_ROOT=/path/to/spack-stack
```

Then inspect the composed configuration:

```bash
cd "$BMATRIX_ROOT"
source scripts/load_jaci_env.sh

CONFIG=configs/jaci-x1.10242.yaml
mpas-bmatrix check-config --config "$CONFIG"
```

The default configuration hierarchy is:

```text
configs/jaci.yaml
  JACI/runtime base and MONAN-JEDI install root

configs/jaci-x1.10242.yaml
  mesh and case-specific static inputs

configs/bmatrix-x1.10242.yaml
  scientific-contract aggregator

configs/bmatrix/x1.10242/*.yaml
  stage-specific scientific fragments
```

## Run from a `mpaswf` manifest

```bash
MANIFEST=/path/to/mpaswf-work/products/mpas-forecast-manifest.tsv

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

## Run from an existing BFLOW workspace

```bash
BFLOW="$WORK_ROOT/bmatrix/bflow_preprocessing/np128_<START_VALID>_<END_VALID>"

PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage vbal \
  --to-stage plots \
  --clean \
  --poll-seconds 30
```

## Documentation

- [End-to-end tutorial](docs/end-to-end-tutorial.md)
- [User guide](docs/user-guide.md)
- [Configuration](docs/configuration.md)
- [JACI quick start](docs/jaci-quickstart.md)
- [Stage products](docs/stage-products.md)
- [mpaswf forecast pairs](docs/mpaswf-pairs.md)
- [Operations](docs/operations.md)
- [B-matrix theory](docs/bmatrix-theory.md)
- [Scientific contract](docs/scientific-contract.md)
- [Developer guide](docs/developer-guide.md)
- [Architecture](docs/architecture.md)
- [Testing](docs/testing.md)

## Development checks

```bash
cd "$BMATRIX_ROOT"
mkdir -p .pytest-tmp

TMPDIR="$BMATRIX_ROOT/.pytest-tmp" \
PYTHONPATH="src:${PYTHONPATH:-}" \
python -m pytest -p no:cacheprovider -q

python -m ruff check src/bmatrix tests
git diff --check
```
