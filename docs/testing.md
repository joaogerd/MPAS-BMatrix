# Testing guide

This document describes how to test `MPAS-BMatrix` changes without running the
full JACI workflow every time.

## 1. Test categories

Use three levels of testing.

### Unit tests

Purpose:

```text
- path resolution;
- configuration parsing;
- YAML rendering helpers;
- product discovery;
- validators with small synthetic files;
- plotting helpers when possible.
```

Unit tests should not require PBS, MPAS-JEDI executables, large NetCDF products
or the JACI filesystem.

### Integration tests

Purpose:

```text
- multiple stage helpers working together;
- synthetic or reduced NetCDF files;
- product contract validation;
- stage planning and resume logic.
```

Integration tests may create temporary workspaces, but they should still avoid
full MPAS-JEDI execution.

### End-to-end JACI checks

Purpose:

```text
- actual PBS submission;
- actual mpasjedi_error_covariance_toolbox.x;
- actual mpasjedi_variational.x;
- full product generation and validation.
```

Run these when changing generated YAML, PBS, scientific stage behavior or
runtime contracts.

## 2. Standard local gate

From the repository root:

```bash
cd "$BMATRIX_ROOT"
mkdir -p .pytest-tmp

TMPDIR="$BMATRIX_ROOT/.pytest-tmp" \
PYTHONPATH="src:${PYTHONPATH:-}" \
python -m pytest -p no:cacheprovider -q

python -m ruff check src/bmatrix tests

git diff --check
```

Use a repository-local temporary directory instead of `/tmp` when working on
systems where `/tmp` is not shared or is aggressively cleaned.

## 3. Environment checks

For JACI-oriented integration checks:

```bash
cd "$BMATRIX_ROOT"
export STACK_ROOT=/path/to/spack-stack
source scripts/load_jaci_env.sh
```

Check that key commands are available:

```bash
which python
which ncdump
which mpiexec || true
which qsub || true
```

Check the package command:

```bash
mpas-bmatrix --help
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix --help
```

## 4. Mocking upstream stages

Because the pipeline is sequential, tests should often mock earlier stages rather
than running them.

Examples:

```text
Testing HDIAG logic:
  create synthetic samplesUnbalanced files and minimal VBAL metadata;
  do not run BFLOW, VBAL or UNBALANCE.

Testing NICAS validation:
  create synthetic mpas.cor_rh.nc, mpas.cor_rv.nc and mpas.stddev.nc;
  verify product discovery and validation behavior.

Testing SO path logic:
  create a fake NICAS merge directory, fake HDIAG stddev and fake VBAL products;
  verify generated paths and failure messages.
```

Synthetic NetCDF files should be as small as possible while preserving the
required dimensions, variable names and attributes needed by the validator under
test.

## 5. Stage-specific test focus

| Stage | Unit/integration focus |
| --- | --- |
| BFLOW | Manifest parsing, product paths, weight path conventions, variable derivation helpers. |
| VBAL | Sample staging, generated YAML structure, product validation, CDF5 checks. |
| UNBALANCE | Input member selection, output naming, validation of `samplesUnbalanced`. |
| HDIAG | Distance/sampling configuration, expected output names, validator failures. |
| NICAS | Per-variable product discovery, merge outputs, 3D/2D grid split invariants. |
| SO | Background enrichment requirements, aliases, expected obsout/an outputs, log success detection. |
| DIRAC | Maintained `dirLats`/`dirLons` + singular selector contract, output validation. |
| PLOTS | Product discovery, figure generation with and without optional map dependencies. |

## 6. Testing generated YAML

Generated YAML is part of the scientific contract. Tests should verify important
keys without snapshotting irrelevant formatting.

Good checks:

```text
- expected SABER blocks are present;
- active variables use canonical names;
- aliases map canonical names to file names;
- Control2Analysis appears after the B blocks;
- NICAS reads split 3D and 2D controls where required;
- DIRAC uses the maintained contract;
- output file names match documented products.
```

Avoid tests that only assert exact long YAML text unless the formatting itself is
the behavior being tested.

## 7. Testing validation failures

Validators should fail clearly when required products are missing or malformed.

For each validator, include tests for:

```text
- all required products present;
- one required product missing;
- wrong or empty file;
- wrong variable/dimension when practical;
- useful error message.
```

## 8. End-to-end smoke checks

Use JACI end-to-end checks for changes that affect scientific execution.

Recommended sequence:

```bash
# From an existing BFLOW workspace.
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage unbalance \
  --to-stage hdiag \
  --clean \
  --poll-seconds 30

PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix build \
  --config "$CONFIG" \
  --bflow-workspace "$BFLOW" \
  --from-stage nicas \
  --to-stage dirac \
  --clean \
  --poll-seconds 30
```

For documentation-only changes, this full smoke is not required. The standard
local gate is sufficient.

## 9. PR checklist

Before submitting a PR, record:

```text
- tests run;
- whether Python package code changed;
- whether scientific YAML changed;
- which stage(s) are affected;
- required rebuild point;
- documentation updated.
```

For documentation-only PRs, state explicitly:

```text
No Python package code or scientific YAML configuration was changed.
```
