# Documentation index

This directory documents `MPAS-BMatrix`, the INPE/MONAN static B-matrix workflow
for MPAS-JEDI/SABER/BUMP background-error covariance products used in the MONAN
atmospheric data-assimilation workflow.

The documentation is separated by audience:

```text
User/operator docs
  first run, execution, resource meanings, validation and products

Scientific/developer docs
  theory, contracts, architecture, tests and extension rules
```

## Start here

For a first run on JACI, read:

**[`getting-started.md`](getting-started.md)**

The recommended operator sequence is:

```bash
mpas-bmatrix setup --site jaci
mpas-bmatrix paths
mpas-bmatrix doctor
mpas-bmatrix check-config
```

The normal first-run interface is intentionally not a list of undocumented
`/path/to/...` exports. Machine/resource paths are resolved transparently and can
still be overridden explicitly for non-standard installations.

## User/operator documentation

| Document | Purpose |
| --- | --- |
| [`getting-started.md`](getting-started.md) | First run on JACI: setup, resource meanings, path resolution and validation. |
| [`resolution-model.md`](resolution-model.md) | Explains user setup, site profiles, resource catalogs, precedence and compatibility fallbacks. |
| [`jaci-quickstart.md`](jaci-quickstart.md) | Short command sequence for an already familiar JACI user. |
| [`user-guide.md`](user-guide.md) | Main execution guide and stage-by-stage operator workflow. |
| [`configuration.md`](configuration.md) | Underlying configuration hierarchy, path meanings, discovery, overrides and rebuild boundaries. |
| [`end-to-end-tutorial.md`](end-to-end-tutorial.md) | Complete system smoke from MPASWF PBS/GFS/WPS/MPAS through final B-matrix diagnostics. |
| [`stage-products.md`](stage-products.md) | Inputs, outputs and acceptance criteria for each MPAS-BMatrix stage. |
| [`mpaswf-pairs.md`](mpaswf-pairs.md) | Forecast-pair hand-off contract between `mpaswf` and MPAS-BMatrix. |
| [`operations.md`](operations.md) | Troubleshooting, validation commands and operational notes. |
| [`diagnostics-and-plots.md`](diagnostics-and-plots.md) | Plot products and visual diagnostics. |

## Scientific/developer documentation

| Document | Purpose |
| --- | --- |
| [`bmatrix-theory.md`](bmatrix-theory.md) | Scientific meaning of the B-matrix and each workflow stage, including explicit UNBALANCE. |
| [`scientific-contract.md`](scientific-contract.md) | Variable names, aliases, SABER/BUMP blocks, `Control2Analysis`, UNBALANCE and DIRAC invariants. |
| [`developer-guide.md`](developer-guide.md) | Developer workflow, extension rules, rebuild rules and PR expectations. |
| [`architecture.md`](architecture.md) | Internal module architecture, configuration layers and stage lifecycle. |
| [`testing.md`](testing.md) | Unit, integration and JACI smoke-testing strategy. |
| [`configuration-audit.md`](configuration-audit.md) | Analysis of the original configuration and its conflicts. |
| [`configuration-reorganization.md`](configuration-reorganization.md) | Configuration ownership and split-layout corrections. |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | Top-level contribution checklist. |
| [`refactoring.md`](refactoring.md) | Historical refactoring notes. |

## Scope

The full operational order is:

```text
mpaswf -> BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

`mpaswf` owns GFS/WPS, MPAS static/init/forecast work and produces the neutral
same-valid-time forecast-pair manifest. MPAS-BMatrix owns:

```text
BFLOW -> VBAL -> UNBALANCE -> HDIAG -> NICAS -> SO -> DIRAC -> PLOTS
```

The full end-to-end smoke deliberately runs **both** workflows so interface or
environment changes are not accepted merely because one component works in
isolation.

## Install MPAS-BMatrix

```bash
git clone https://github.com/joaogerd/MPAS-BMatrix.git
cd MPAS-BMatrix
python -m pip install -e .
```

The public user command is:

```text
mpas-bmatrix
```

Developer/debug documentation may also use `python -m bmatrix`, but operator
documentation uses the installed command.

## Current validated case

The global `x1.10242` case now has two resolution contracts before the existing
scientific configuration hierarchy:

```text
configs/sites/jaci.yaml
configs/resources/x1.10242.yaml
        ↓
configs/jaci.yaml
configs/jaci-x1.10242.yaml
configs/bmatrix-x1.10242.yaml
configs/bmatrix/x1.10242/*.yaml
```

The site profile describes machine/path resolution policy. The resource catalog
describes the logical x1.10242 resource. The lower YAML hierarchy remains the
scientific/runtime configuration consumed by the pipeline.

Normal users do not need to understand all layers before the first `doctor` run.
All layers remain visible for review and reproducibility.

The current deterministic work layout is:

```text
<WORK_ROOT>/bmatrix/
├── bflow_preprocessing/<RUN>/
├── covariance/
│   ├── vbal/<RUN>/
│   ├── unbalance/<RUN>/
│   ├── hdiag/<RUN>/
│   ├── nicas/<RUN>/
│   ├── so/<RUN>/
│   └── dirac/<RUN>/
└── plots/<RUN>/
```

Use:

```bash
mpas-bmatrix paths
```

to see infrastructure/resource paths and:

```bash
mpas-bmatrix products --bflow-workspace /path/to/BFLOW_WORKSPACE
```

to see reusable scientific products from a specific run.
