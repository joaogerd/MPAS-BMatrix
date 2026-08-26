# Runtime resolution model

MPAS-BMatrix separates three questions that must not be conflated:

1. **What site am I running on?**
2. **What logical scientific resource am I using?**
3. **Where are this site's/runtime's physical files?**

The `doctor` answers none of those by guessing the filesystem. It validates the
result of the resolution layers described below.

## Layers

```text
user choices / explicit overrides
              +
         site profile
              +
       resource catalog
              ↓
      resolved configuration
              ↓
            doctor
```

### User setup

Normal JACI setup stores semantic choices in:

```text
~/.config/mpas-bmatrix/setup.yaml
```

Example:

```yaml
site: jaci
workspace: /p/projetos/monan_das/maria.silva/work/MPAS-BMatrix
resource: x1.10242
```

A user with a non-standard private installation can add only the paths that are
different. The CLI can persist those overrides through `setup`, for example:

```bash
mpas-bmatrix setup --site jaci \
  --monan-jedi-install /custom/install/monan-jedi
```

This produces an explicit override instead of teaching the resolver another
person-specific filesystem convention.

### Site profile

Site profiles live under:

```text
configs/sites/
```

The JACI profile is:

```text
configs/sites/jaci.yaml
```

A site profile describes machine policy and resolution rules. It may eventually
contain canonical shared paths maintained by the site. Until those paths are
published, current per-user JACI conventions are retained only as
`compatibility_candidates`/`compatibility_globs`.

Whenever one of those transitional rules is used, `mpas-bmatrix paths` reports:

```text
source: compatibility-fallback
```

This is intentionally different from `source: site-profile`.

### Resource catalog

Resource catalogs live under:

```text
configs/resources/
```

For the current case:

```text
configs/resources/x1.10242.yaml
```

The catalog describes **what the resource is**, not where a user stores it. It
records the logical mesh, vertical-level contract, expected static inputs,
required executables and MPAS runtime files.

This separation allows the same `x1.10242` scientific resource to be used on a
second site without copying JACI paths into the scientific configuration.

## Resolution precedence

For runtime roots the current precedence is:

```text
explicit environment override
        ↓
saved user override
        ↓
canonical path declared by site profile (when one exists)
        ↓
command probe from the active environment
        ↓
compatibility fallback
        ↓
unresolved
```

For the workspace:

```text
explicit setup argument
        ↓
WORK_ROOT environment override
        ↓
saved user workspace
        ↓
site-profile workspace default
```

The resolver never recursively searches arbitrary project trees.

## What another user needs to configure

A normal user on a fully provisioned site should configure only:

```text
site
workspace (optional; site default is normally enough)
resource (optional when the site has a default)
```

A user with a different/private layout configures only the roots that cannot be
provided by the site profile or active environment:

```text
MONAN_JEDI_INSTALL
MPAS_MESH_ROOT
MPAS_JEDI_STATIC_ROOT
MONAN_JEDI_SOURCE   (transitional)
STACK_ROOT
```

Equivalent setup flags are available for these advanced overrides. Environment
variables remain supported for one-off/developer use.

## What `doctor` proves

`doctor` receives the selected site/resource plus the composed MPAS-BMatrix
configuration. It then checks:

- logical resource metadata against the selected resource catalog;
- required files/directories at the resolved paths;
- execute permission for required programs;
- the MPI partition implied by the configured rank count;
- MPAS static/runtime tables declared by the resource catalog.

A final `READY` therefore means the resolved preflight prerequisites are
present. It does not replace the full PBS/end-to-end validation.

## Target JACI end state

The current compatibility fallbacks are transitional. Once a canonical shared
JACI runtime/resource publication exists, `configs/sites/jaci.yaml` can point to
those stable site paths and the private fallback rules can be removed without
changing the scientific catalog or the user-facing workflow.
