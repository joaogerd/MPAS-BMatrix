# Mesh-independent covariance campaigns

Forecast generation belongs to MPASWF. BMatrix consumes its f048/f024 manifest;
the geometry used by covariance stages must agree with those states.

In the BMatrix case YAML, declare the chosen mesh, `mesh.nvertlevels`, grid,
graph, partitions directory and `mesh.nproc`. They must describe the supplied
states/invariant; changing names does not convert a NetCDF mesh or level count.

Provide reviewed geometry files explicitly, independently of the tutorial:

```yaml
static:
  invariant: /absolute/path/to/x1.2621442.invariant.nc
  namelist: /absolute/path/to/15km/namelist.atmosphere
  streams: /absolute/path/to/15km/streams.atmosphere
  support_dir: /absolute/path/to/15km/support
  # Keep the case's existing geovars and keptvars declarations.
```

Paths follow the existing BMatrix path convention; prefer absolute paths.
`support_dir` supplies stream lists and optional support files. Physics tables
continue to come from `install.atmosphere_share` when configured. The historical
`static.tutorial_physics_files` is an accepted alias for the support directory.

VBAL stages geometry under neutral names `namelist.atmosphere` and
`streams.atmosphere`, sets the background valid time and decomposition prefix,
and points the invariant stream at the selected mesh. HDIAG, NICAS, DIRAC, SO,
UNBALANCE and the HDIAG comparison utility use these same neutral staged names.
The configured partition is required rather than silently omitted.

For x1.10242 only, old input names ending in `_240km` remain a compatibility
fallback. A new mesh cannot select that fallback implicitly. Explicit files
and their scientific settings must still be reviewed for the chosen case.

Use a new work root for a new mesh/campaign. Existing covariance workspaces
created with the old staged `_240km` names must be prepared again from VBAL
through downstream stages; do not resume directly into an old workspace.
Check all scientific stage fragments as well as the platform YAML: length
scales, sampling, interpolation settings, level selections and DIRAC tests are
case choices, not settings automatically inferred from the new mesh name.

Before a long campaign, validate one MPASWF pair and run BMatrix scientific
preflight with the matching case YAML and manifest. Then validate the generated
covariance products on JACI. Unit/staging tests do not execute MPAS or SABER.
