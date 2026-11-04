# MPAS-BMatrix case-independence audit (2026-11-04)

## Scope

The MPAS-BMatrix runtime starts at the NMC/BFLOW producer-consumer boundary
and includes BFLOW, VBAL, HDIAG, NICAS, SO, DIRAC and plots. This audit reviews
the public CLI, composed YAML loader, installed MONAN-JEDI runtime contract,
preflight, mesh geometry checks, static atmosphere staging, samples/workspaces,
diagnostics and compatibility tooling.

The scientific parameters for one experiment belong to a composed case YAML
and stage fragments; the Python library must not silently choose x1.10242
or reuse another mesh's saved products.

## Findings and resolution

| Area | Former risk / original behavior | Implemented or intentionally retained |
| --- | --- | --- |
| CLI case selection | `mpas-bmatrix` commands silently selected `configs/jaci-x1.10242.yaml` | `--config` is now required for operational commands, including diagnostic A/B entrypoints. The producer manifest can still be checked alone. |
| Legacy namelist/streams | VBAL could look for `_240km` names under a tutorial directory | New cases explicitly select `static.namelist` / `static.streams` or neutral files under `static.support_dir`. The old fallback is retained only for the old tutorial configuration. |
| Static stream lists | Every `stream_list.atmosphere.*` in a tutorial directory was staged | Modern cases link only `static.stream_lists` or files discovered in the chosen XML. Control stream list is generated from scientific controls. The original case lists its files explicitly. |
| Preflight | Missing case files could be reported as `static.tutorial_physics_files` even when never configured | Checks report actual editable scientific YAML fields; human CLI now prints problems and corrective actions, with `--json` for machine data and `--verbose` for passed checks. |
| Mesh geometry | Incorrect dimensions and mesh identity could contaminate NMC training | Scientific NMC preflight checks canonical NetCDF geometry, vertical levels, valid times and forecast pair compatibility. |
| Sampling levels | VBAL/HDIAG reduced levels and NICAS diagnostic levels copied from 55-level case might be invalid for another vertical grid | Preflight checks those configured values lie within `mesh.nvertlevels` and identifies the exact stage field. Scientific appropriateness must still be reviewed. |
| MPI defaults | Helpers silently assumed 64 ranks when `mesh.nproc` absent | `mesh.nproc` is explicit and validated; partitions are chosen from its actual value. |
| Diagnostics | Main and A/B CLIs assumed x1.10242, plots implicitly chose level index 30 | Diagnostic entrypoints require `--config`; plot default derives from half of the configured number of vertical levels. |
| Workspace isolation | Date range + rank count alone produced identical paths for different meshes | Workspace identifier now includes `mesh.name` or `project.case_id`, propagated downstream. Use separate work roots / case IDs for distinct physical configurations. |
| Scientific-stage parameters | Reduced levels, NICAS coarsening, H/V scales, wind transforms, synthetic observations were embedded in the x1.10242 stage YAML | The **complete original scientific contract** is copied, unchanged, under `testcase/tutorial-240km/stages/`. New cases must review and edit those values; arbitrary physical defaults are not inferred. |
| Legacy PBS scripts | The repository contains three hard-coded MPAS smoke/init/forecast templates under `templates/pbs/` | These are historical diagnostic templates, **not** used by the BMatrix production pipeline. They remain only for historical compatibility; production forecasts are exclusively MPASWF's responsibility. |

## Standalone 240-km scientific testcase

The independently selected
[`testcase/tutorial-240km/`](../testcase/tutorial-240km/README.md)
contains:

- `jaci.yaml`: mesh, data files, explicit namelist/streams, JACI/site include.
- `bmatrix.yaml`: scientific aggregation of eight case-specific fragments.
- `stages/*.yaml`: original controls, BFLOW, VBAL, optional UNBALANCE,
  HDIAG, NICAS, SO and DIRAC settings **without changes to scientific values**.
- `run.sh`: check, dry-run or full build using the MPASWF-produced manifest.

CI checks YAML composition and scientific-fragment equality with the
historical configuration. This protects the scientific reference when the
generic code evolves.

## Explicitly not generalized

- The current NMC manifest/producer agreement uses two same-valid-time
  forecasts with f048/f024 columns and the corresponding BFlow perturbation
  definition. Supporting other lead pairs would require a jointly versioned
  MPASWF/BMatrix contract change.
- This tool targets **MPAS-JEDI/SABER/BUMP** operators, MPAS-compatible mesh
  data and a configured runtime installation. It is generic across compatible
  MPAS meshes, not arbitrary atmospheric model cores.
- Original case numerical parameters are not automatically resized or
  optimized for another resolution. They remain scientific choices.
- `x1.10242` and `_240km` references in legacy compatibility and historical
  docs/scripts do not determine the default for new experiments.

## Validation boundary / outstanding scientific acceptance

Python CI validates composition, deterministic paths, errors, scientific
contracts and unit-scale numerical operations, but cannot launch JACI or
compute SABER covariance products in this environment. We have **not**
established bitwise reproducibility of old calibration results.

For full validation, freeze the MPASWF input states and external software
versions, run the complete testcase on JACI, compare BFLOW perturbations
and each VBAL/HDIAG/NICAS/SO/DIRAC NetCDF product to archived references,
and record tolerances and runtime metadata. Different sample periods or
resolutions should produce **different** calibrated B matrices.
