# Developer Guide

This guide is for maintainers and contributors who need to understand, modify or
extend the `MPAS-BMatrix` codebase.

For execution-oriented instructions, read [`user-guide.md`](user-guide.md). For
stage outputs and acceptance criteria, read [`stage-products.md`](stage-products.md).

## 1. Development priorities

This repository implements a sequential scientific pipeline. The main design
priority is preserving the scientific contract between stages.

When changing the code, protect these properties:

1. stage order is explicit and reproducible;
2. each production stage validates its inputs and outputs;
3. file names and variable aliases remain consistent across stages;
4. scientific transforms may remain in memory when no persistent intermediate
   product is required;
5. user-facing documentation stays separate from implementation details;
6. changes that alter scientific outputs are tested from the earliest affected
   stage onward.

## 2. Repository responsibilities

`MPAS-BMatrix` owns the production stages from BFLOW onward:

```text
BFLOW -> VBAL -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

It does not own MPAS forecast production. GFS/WPS, MPAS initialization,
forecast integration and same-valid-time f024/f048 pair production are upstream
responsibilities, usually handled by `mpaswf`.

The retained `unbalance_core` is a migration/regression utility, not a production
stage.

## 3. Documentation split

| Audience | Documents | Content |
| --- | --- | --- |
| User/operator | `README.md`, `user-guide.md`, `jaci-quickstart.md`, `stage-products.md`, `operations.md` | How to run, what files are required, what products are generated, how to validate and troubleshoot. |
| Developer/maintainer | `developer-guide.md`, `architecture.md`, `testing.md`, `refactoring.md` | Code structure, stage orchestration, tests and maintenance rules. |
| Scientific maintainer | `bmatrix-theory.md`, `scientific-contract.md`, `in-memory-vbal-hdiag.md` | Mathematical meaning, variable aliases, scientific contracts and migration validation. |

## 4. Main code organization

The package is organized around one public command:

```bash
mpas-bmatrix
```

Important modules:

```text
src/bmatrix/cli.py
  Public CLI and subcommand parsing.

src/bmatrix/pipeline.py
  Production stage graph, planning and orchestration.

src/bmatrix/*_core/
  Stage-specific prepare/submit/validate/product handling.

src/bmatrix/plots_core/
  Local post-processing and diagnostic figures.
```

## 5. Pipeline architecture

A production stage may only run after required upstream products exist and pass
validation. Conceptually each stage owns prepare, submit/run, validate and
product resolution.

For the current VBAL/HDIAG interface:

```text
VBAL
  calibrates BUMP_VerticalBalance and sampling

HDIAG
  reads original centered NMC samples
  reads VBAL/sampling products
  applies inverse BUMP_VerticalBalance in memory
  calibrates BUMP_NICAS diagnostics
```

There is no production `samplesUnbalanced` product interface.

## 6. Scientific theory and equations

The conceptual factorization is:

```text
B ≈ C2A · VBAL · StdDev · NICAS · StdDev · VBALᵀ · C2Aᵀ
```

Read [`bmatrix-theory.md`](bmatrix-theory.md) and
[`scientific-contract.md`](scientific-contract.md) before changing controls,
aliases, NICAS groups, VBAL relations or `Control2Analysis` variables.

## 7. Internal data contracts

Canonical JEDI/SABER names are mapped explicitly to NetCDF names, for example:

```yaml
- in code: air_temperature
  in file: temperature
- in code: water_vapor_mixing_ratio_wrt_moist_air
  in file: spechum
```

Aliases apply to SABER/BUMP product reads, not to the MPAS stream parser. MPAS
streams must remain Registry-native.

## 8. Adding or modifying a stage

Before changing a production stage, identify its upstream products, outputs,
downstream consumers, acceptance criteria, execution model and scientific impact.

Add a stage to `bmatrix.pipeline.STAGES` only when it is part of the official
sequential production contract. Diagnostic or migration utilities should remain
outside that graph.

## 9. Rebuild rules for scientific changes

| Change | Rebuild from |
| --- | --- |
| MPAS forecast pairs, manifest, mesh or BFLOW variable preparation | BFLOW |
| Control variables, aliases or dimensions | BFLOW |
| VBAL relations, VBAL sampling or inverse-balance contract | VBAL |
| HDIAG sampling, variance or fitting parameters | HDIAG |
| NICAS resolution, local products or merge behavior | NICAS |
| SO observations or variational validation only | SO |
| DIRAC impulse configuration only | DIRAC |
| Plot style or plotting logic only | PLOTS |

Changes to the legacy `unbalance_core` affect only A/B migration tests unless the
production architecture is deliberately changed again.

## 10. Development environment

```bash
cd "$BMATRIX_ROOT"
python -m pip install -e ".[dev,diagnostics]"
```

On JACI, load the stack before integration workflows:

```bash
export STACK_ROOT=/path/to/spack-stack
source scripts/load_jaci_env.sh
```

## 11. Tests and static checks

The standard local gate is:

```bash
cd "$BMATRIX_ROOT"
mkdir -p .pytest-tmp
TMPDIR="$BMATRIX_ROOT/.pytest-tmp" \
PYTHONPATH="src:${PYTHONPATH:-}" \
python -m pytest -p no:cacheprovider -q
python -m ruff check src/bmatrix tests
git diff --check
```

Changes to the VBAL/HDIAG scientific path additionally require the A/B check in
[`in-memory-vbal-hdiag.md`](in-memory-vbal-hdiag.md).

## 12. Pull request expectations

A PR that changes behavior should state which stages changed, whether scientific
products changed, the required rebuild point, tests executed, documentation
updated and compatibility of existing products. For this migration, include the
HDIAG/NICAS/DIRAC/SO A/B results before merge.
