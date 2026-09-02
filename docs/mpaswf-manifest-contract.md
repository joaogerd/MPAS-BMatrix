# mpaswf -> MPAS-BMatrix manifest contract

`mpaswf` is the producer of the MPAS forecast pairs used by BFLOW.  The
current producer writes:

```text
valid_time	f048_state	f024_state	f048_restart	f024_restart
```

For every valid time `T`:

- `f048_state` is the MPAS-JEDI `da_state` (`mpasout.*.nc`) from the forecast
  initialized at `T - 48 h`;
- `f024_state` is the MPAS-JEDI `da_state` (`mpasout.*.nc`) from the forecast
  initialized at `T - 24 h`;
- `f048_restart` and `f024_restart` are retained for traceability and restart
  workflows, but BFLOW does not use them to compute NMC perturbations.

`MPAS-BMatrix` maps the state columns to its internal `f048` and `f024` pair.
The legacy three-column producer schema remains accepted:

```text
valid_time	f048	f024
```

Before BFLOW, validate the exact producer manifest:

```bash
mpas-bmatrix check-manifest \
  --manifest /p/projetos/monan_das/$USER/work/mpaswf/products/mpas-forecast-manifest.tsv
```

Acceptance requires at least four strictly increasing valid times and readable,
non-empty, distinct f048/f024 state files for every pair.

Then inspect the side-effect-free workflow plan:

```bash
mpas-bmatrix build \
  --config configs/jaci-x1.10242.yaml \
  --manifest /p/projetos/monan_das/$USER/work/mpaswf/products/mpas-forecast-manifest.tsv \
  --from-stage bflow \
  --to-stage plots \
  --dry-run
```

Only after both commands pass should BFLOW create a workspace or generate ESMF
weights/products.
