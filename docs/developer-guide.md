# Developer Guide

This guide is for maintainers and contributors who need to understand, modify or
extend the `MPAS-BMatrix` codebase.

For execution-oriented instructions, read [`user-guide.md`](user-guide.md). For
stage outputs and acceptance criteria, read [`stage-products.md`](stage-products.md).

## 1. Development priorities

This repository implements a sequential scientific pipeline. The main design
priority is not just running jobs; it is preserving the scientific contract
between stages.

When changing the code, protect these properties:

1. stage order is explicit and reproducible;
2. each stage validates its inputs and outputs;
3. file names and variable aliases remain consistent across stages;
4. user-facing documentation stays separate from implementation details;
5. scientific formulas and contracts are documented outside the code path where
   possible;
6. changes that alter scientific outputs are tested from the earliest affected
   stage onward.

## 2. Repository responsibilities

`MPAS-BMatrix` owns stages from BFLOW onward:

```text
BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

It does not own MPAS forecast production. GFS/WPS, MPAS initialization,
forecast integration and same-valid-time f024/f048 pair production are upstream
responsibilities, usually handled by `mpaswf`.

## 3. Documentation split

Keep the documentation separated by audience:

| Audience | Documents | Content |
| --- | --- | --- |
| User/operator | `README.md`, `user-guide.md`, `jaci-quickstart.md`, `stage-products.md`, `operations.md` | How to run, what files are required, what products are generated, how to validate and troubleshoot. |
| Developer/maintainer | `developer-guide.md`, `architecture.md`, `testing.md`, `refactoring.md` | Code structure, stage orchestration, adding stages, tests and maintenance rules. |
| Scientific maintainer | `bmatrix-theory.md`, `scientific-contract.md` | Mathematical meaning, variable aliases, invariant scientific contracts and rebuild rules. |

Do not put dense SABER/BUMP theory in the user guide. Do not hide scientific
contracts only in implementation code.

## 4. Main code organization

The package is organized around one public command:

```bash
mpas-bmatrix
```

The equivalent module invocation used in development is:

```bash
PYTHONPATH="src:${PYTHONPATH:-}" python -m bmatrix <command>
```

Important modules:

```text
src/bmatrix/cli.py
  Public CLI and subcommand parsing.

src/bmatrix/pipeline.py
  Stage graph, stage order, planning and orchestration.

src/bmatrix/*_core/
  Stage-specific logic for prepare/submit/validate/product handling.

src/bmatrix/scheduler/
  PBS submission, polling and progress display.

src/bmatrix/plots_core/
  Local post-processing and diagnostic figures.
```

See [`architecture.md`](architecture.md) for the detailed module map.

## 5. Pipeline architecture

The pipeline is dependency ordered. A stage may only run after its required
upstream products exist and pass validation.

Conceptually, each stage should expose these responsibilities:

```text
prepare
  create workspace, links, generated YAML, generated PBS and manifests

submit/run
  submit PBS or run local stage

validate
  verify generated products and stage-specific acceptance criteria

products
  report or resolve outputs consumed downstream
```

Implementation details may vary by stage, but the user contract should remain
consistent.

## 6. Scientific theory and equations

The theoretical meaning of the B-matrix and each stage lives in
[`bmatrix-theory.md`](bmatrix-theory.md). The main conceptual factorization is:

```text
B ≈ C2A · VBAL · StdDev · NICAS · StdDev · VBALᵀ · C2Aᵀ
```

This guide should not duplicate the full theory. It should point contributors to
where the theory is defined and explain how code changes interact with it.

When modifying a scientific stage, update or verify:

```text
bmatrix-theory.md
scientific-contract.md
stage-products.md
unit/integration tests
example commands in user-guide.md
```

## 7. Internal data contracts

The most important internal contract is the variable-name mapping between
canonical JEDI/SABER names and names stored in NetCDF products.

Examples:

```yaml
- in code: air_temperature
  in file: temperature
- in code: water_vapor_mixing_ratio_wrt_moist_air
  in file: spechum
- in code: air_pressure_at_surface
  in file: surface_pressure
```

Rules:

1. `in code` is the canonical name expected by MPAS-JEDI/SABER/OOPS.
2. `in file` is the name found in B-matrix NetCDF products.
3. Aliases apply to SABER/BUMP product reads.
4. Aliases do not translate names for the MPAS stream parser.
5. MPAS streams must remain MPAS Registry-native.

Read [`scientific-contract.md`](scientific-contract.md) before changing aliases,
control variables, NICAS groups, VBAL relations or `Control2Analysis` variables.

## 8. Adding or modifying a stage

Before adding a new stage or modifying an existing one, answer these questions:

```text
1. What upstream products does the stage consume?
2. What files does it produce?
3. Which downstream stages consume those files?
4. What is the acceptance criterion for a successful run?
5. Is the stage local, PBS-based, or both?
6. Does the stage change scientific outputs?
7. What tests can isolate the new behavior?
```

Recommended implementation checklist:

```text
1. Add the stage to the stage graph in the pipeline only if it is part of the
   official sequential contract.
2. Implement workspace preparation separately from job submission.
3. Render generated YAML/PBS deterministically.
4. Write or update a stage manifest where appropriate.
5. Add a validator that checks product existence and structure.
6. Add tests for path planning, generated command/YAML structure and validation
   behavior.
7. Update user-guide.md and stage-products.md.
8. Update developer-guide.md, architecture.md or scientific-contract.md if the
   change affects internals or theory.
```

## 9. Rebuild rules for scientific changes

Use this rule of thumb:

| Change | Rebuild from |
| --- | --- |
| MPAS forecast pairs, manifest, mesh or BFLOW variable preparation | BFLOW |
| Control variables, aliases or dimensions | BFLOW |
| VBAL relations or VBAL sampling | VBAL |
| UNBALANCE transform or member handling | UNBALANCE |
| HDIAG sampling, variance or fitting parameters | HDIAG |
| NICAS resolution, local products or merge behavior | NICAS |
| SO observations or variational validation only | SO |
| DIRAC impulse configuration only | DIRAC |
| Plot style or plotting logic only | PLOTS |

When in doubt, rebuild from the earliest affected stage.

## 10. Development environment

Basic editable install:

```bash
cd "$BMATRIX_ROOT"
python -m pip install -e .
```

Development install:

```bash
python -m pip install -e ".[dev,diagnostics]"
```

Optional runtime extras depend on the activity:

```bash
python -m pip install -e ".[weights,bflow]"
```

On JACI, load the stack before running integration workflows:

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

See [`testing.md`](testing.md) for testing strategy, mocking guidance and the
difference between unit, integration and JACI end-to-end checks.

## 12. Pull request expectations

A PR that changes behavior should state:

```text
- which stage changed;
- whether scientific products changed;
- which rebuild point is required;
- which tests were run;
- whether documentation was updated;
- whether existing products are still compatible.
```

A documentation-only PR should state that no Python package code or scientific
YAML configuration was changed.
