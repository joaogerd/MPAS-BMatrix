from __future__ import annotations

from pathlib import Path

from bmatrix.preflight import preflight_payload


def _executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


def _config(tmp_path: Path) -> dict[str, object]:
    project = tmp_path / "project"
    project.mkdir()
    loader = project / "scripts/load_jaci_env.sh"
    loader.parent.mkdir()
    loader.write_text("#!/bin/sh\n", encoding="utf-8")

    work_parent = tmp_path / "work"
    work_parent.mkdir()

    stack = tmp_path / "spack-stack"
    (stack / "configs/sites/tier2/jaci").mkdir(parents=True)
    (stack / "configs/sites/tier2/jaci/setup.sh").write_text("# setup\n")
    (stack / "envs/jaci-mpas-jedi-gcc12-craympich/modules").mkdir(parents=True)

    install = tmp_path / "install"
    _executable(install / "bin/mpasjedi_error_covariance_toolbox.x")
    _executable(install / "bin/mpasjedi_variational.x")
    (install / "share/MPAS/core_atmosphere").mkdir(parents=True)
    namelists = install / "share/monan-jedi/mpas-jedi/namelists"
    namelists.mkdir(parents=True)
    (namelists / "geovars.yaml").write_text("geovars: []\n")
    (namelists / "keptvars.yaml").write_text("keptvars: []\n")

    mesh = tmp_path / "mesh"
    mesh.mkdir()
    grid = mesh / "x1.test.grid.nc"
    graph = mesh / "x1.test.graph.info"
    grid.write_bytes(b"grid")
    graph.write_bytes(b"graph")
    partitions = mesh / "partitions"
    partitions.mkdir()
    (partitions / "x1.test.graph.info.part.4").write_bytes(b"partition")

    static = tmp_path / "static"
    static.mkdir()
    invariant = static / "x1.test.invariant.nc"
    invariant.write_bytes(b"invariant")
    physics = static / "physics"
    physics.mkdir()

    return {
        "project": {
            "project_root": str(project),
            "work_root": str(work_parent / "MPAS-BMatrix"),
        },
        "environment": {
            "loader": "scripts/load_jaci_env.sh",
            "variables": {"STACK_ROOT": str(stack)},
        },
        "install": {
            "root": str(install),
            "atmosphere_share": str(install / "share/MPAS/core_atmosphere"),
        },
        "mesh": {
            "name": "x1.test",
            "grid": str(grid),
            "graph": str(graph),
            "partitions_dir": str(partitions),
            "nproc": 4,
        },
        "static": {
            "invariant": str(invariant),
            "tutorial_physics_files": str(physics),
            "geovars": str(namelists / "geovars.yaml"),
            "keptvars": str(namelists / "keptvars.yaml"),
        },
    }


def test_preflight_accepts_complete_runtime_contract(tmp_path: Path) -> None:
    payload = preflight_payload(_config(tmp_path))

    assert payload["valid"] is True
    checks = {item["name"]: item for item in payload["checks"]}
    assert checks["project.work_root"]["status"] == "CREATABLE"
    assert checks["environment.variables.STACK_ROOT"]["status"] == "OK"
    assert checks["install.error_covariance_toolbox"]["status"] == "OK"
    assert checks["install.variational"]["status"] == "OK"
    assert checks["mesh.partition"]["status"] == "OK"


def test_preflight_fails_early_for_missing_runtime_executable(tmp_path: Path) -> None:
    config = _config(tmp_path)
    install = Path(str(config["install"]["root"]))  # type: ignore[index]
    (install / "bin/mpasjedi_variational.x").unlink()

    payload = preflight_payload(config)

    assert payload["valid"] is False
    checks = {item["name"]: item for item in payload["checks"]}
    assert checks["install.variational"]["status"] == "MISSING"
