# Contributing to MPAS-BMatrix

Thank you for contributing to `MPAS-BMatrix`.

This repository implements a sequential scientific workflow. Contributions must
preserve both the software behavior and the scientific contract between stages.

Start here:

```text
docs/developer-guide.md
docs/architecture.md
docs/testing.md
docs/scientific-contract.md
```

Before opening a pull request, run:

```bash
cd "$BMATRIX_ROOT"
mkdir -p .pytest-tmp

TMPDIR="$BMATRIX_ROOT/.pytest-tmp" \
PYTHONPATH="src:${PYTHONPATH:-}" \
python -m pytest -p no:cacheprovider -q

python -m ruff check src/bmatrix tests

git diff --check
```

In your PR description, state:

```text
- which stage changed;
- whether Python package code changed;
- whether scientific YAML changed;
- whether scientific products are expected to change;
- required rebuild point;
- tests run;
- documentation updated.
```

For documentation-only PRs, explicitly state:

```text
No Python package code or scientific YAML configuration was changed.
```
