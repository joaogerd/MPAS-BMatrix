# Second audit: resolution, vertical levels and scientific case isolation
**Date:** 2026-11-05

This is a code-level audit of current production modules, composed YAML,
NetCDF/ESMF interfaces and the archived
[240-km scientific testcase](../testcase/tutorial-240km/README.md). It is not
a full JACI numerical comparison.

## Scope checked

`bflow_core`, `esmf_weights`, `nmc_core`, `vbal_core`, `hdiag_core`,
`nicas_core`, `so_core`, `dirac_core`, `unbalance_core`,
`plots_core`, `scheduler`, `artifacts`, `preflight`, `pipeline`,
`config`, `scientific_config`, CLI and original testcase fragments.

The audit looked for dependence on x1.10242, 240 km, 55 levels, 64/128
ranks, fixed model time step, f024/f048 pairs, default diagnostic levels,
NetCDF dimensions, scientific-output filenames, and old-workspace reuse.

## Corrections verified by regression tests

| Finding | Correction |
| --- | --- |
| The NMC path generator silently used `config_dt=60` if not configured | A date-range request now requires `runtime.config_dt` or `--dt`, with positive-integer validation. A producer manifest does not need this guessed path. |
| Multiple PBS stages fell back to `pbs.nproc` or even one MPI process | A shared `configured_mpi_ranks()` requires `mesh.nproc`; all VBAL/HDIAG/NICAS/SO/DIRAC/UNBALANCE job renderers use it. Deliberately serial NICAS merging remains serial. |
| NICAS assumed `dirac_level_from_top=20` and silently clamped out-of-range levels | For configured impulse locations the scientific parameter must be explicit and between 1 and `mesh.nvertlevels`. Invalid levels fail with an actionable error. |
| NICAS assumed `surface_pressure` was the only 2-D field | It now derives 2d/3d status from each declared `controls[].dimensions`; arbitrary named 2-D controls get level 1 and 3-D controls use the selected model level. |
| VBAL/legacy UNBALANCE assumed `dominant_mode=20` | `vbal.dominant_mode` must now be explicit and between 1 and `mesh.nvertlevels`. |
| Standalone plot API defaulted to vertical index 30 | If omitted it inspects available NetCDF products and selects their middle vertical level; inconsistent product level counts are reported. |
| Manifest filename contract remains f048/f024, while the case YAML could declare other leads | Manifest-driven BFLOW refuses contradictory `bflow.nmc.older_lead_hours` / `newer_lead_hours`. A v2 producer/consumer contract would be required for arbitrary lead pairs. |
| Old product scientific identity only checked horizontal and vertical mesh geometry | New stage manifests include `scientific_settings_sha256`, hashing selected scientific YAML and any explicitly configured local atmosphere text files. Different physics or BUMP settings cannot be treated as the same scientific case. Old geometry-only identities remain readable with an explicit warning. |

## Important coupling found but *not* silently generalized

**1. Scientific product naming.**
Several downstream consumers expect filenames including
`mpas_vbal.nc`, `mpas_sampling.nc`, `mpas.stddev.nc`,
`mpas.cor_rh.nc`, `mpas_nicas.nc` and `mpas.dirac.nc`, even though
individual BUMP stages expose `files_prefix` in YAML.

Custom `vbal.files_prefix`, `hdiag.files_prefix` or
`nicas.files_prefix` values are **not an end-to-end supported feature**.
The composed YAML loader now rejects non-`mpas` prefixes explicitly rather
than letting downstream stages fail after substantial computation.
To make this truly generic, introduce a unified versioned artifact naming
contract and propagate it through all stage renderers, validators, plotting,
BMatrixProducts and the SABER handoff. This remains open work.

**2. Training sample identity.**
The default BFLOW workspace includes mesh/case ID, rank count, and the first
and last valid times, but it does **not** include the full producer-manifest
checksum or sample membership. Two runs with identical bounds/mesh but
different intermediate sample dates can still choose the same BFLOW path.
Use distinct `project.case_id` or `project.work_root` until workspace
provenance includes manifest content.

**3. Input content provenance.**
The scientific-settings signature guards YAML choices but does not yet hash
all potentially huge NMC input NetCDF files. Changing a state at the same
file path may require a manual workspace reset. The producer's manifest SHA,
per-sample source digests and calibrated-stage product checksums should
eventually form a versioned provenance chain.

**4. NMC method is intentionally specialized.**
The producer-consumer manifest v1 is f048/f024 and BUMP/NICAS has a
minimum four-member diagnostic/operational guard. These are method/contract
constraints, not mesh-resolution literals. General lead pairs and tiny
smoke-test-only sample sets should use separate explicit workflows, not silent
parameter guessing.

**5. Case physics are intentionally configured, not auto-scaled.**
The archived testcase preserves 55 model levels, VBAL sampling 55,
HDIAG reduced levels 10, NICAS resolution/coarsening 8, temporary 1-degree
lat-lon wind-transform grid, geographical DIRAC points, and the selected
horizontal/vertical correlation parameters. Some are valid ranges and now
validated; their *scientific appropriateness* for 15/60 km must be assessed
with actual sample diagnostics and model grid metadata.

**6. Platform and installed BUMP/SABER remain explicit dependencies.**
The program assumes MPAS-compatible NetCDF state dimensions/fields, MPAS-JEDI
operators and installed binaries. This is generic for compatible MPAS cases,
not arbitrary model cores or any NetCDF file.

## Acceptance tests required on JACI

1. Select a new mesh and correct `nvertlevels`, graph partition, invariant,
   namelist, streams and controls; run the composed `check-config`.
2. Produce at least four valid same-time NMC f048/f024 pairs with MPASWF;
   run `check-manifest --config` to verify horizontal/vertical geometry.
3. Run BFLOW through DIRAC and confirm valid scientific products on the
   selected mesh and input period, including 2-D and 3-D controls.
4. Run the archived tutorial using frozen binaries/input datasets and compare
   numerical products stage by stage to trusted references.
5. Vary mesh, vertical level count, model time step, MPI decomposition and
   valid-time spacing independently; reject any mixed/cross-campaign products.

GitHub Actions tests do not execute full MPAS integrations or SABER/BUMP HPC
calibration and therefore cannot certify the scientific performance of 15 km.
