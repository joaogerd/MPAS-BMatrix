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



def test_preflight_rejects_omitted_mandatory_static_and_mesh_resources(tmp_path: Path) -> None:
    config = _config(tmp_path)
    mesh = config["mesh"]  # type: ignore[index]
    static = config["static"]  # type: ignore[index]
    del mesh["graph"]  # type: ignore[index]
    del mesh["partitions_dir"]  # type: ignore[index]
    del static["invariant"]  # type: ignore[index]
    del static["geovars"]  # type: ignore[index]
    del static["keptvars"]  # type: ignore[index]
    del static["tutorial_physics_files"]  # type: ignore[index]

    payload = preflight_payload(config)

    assert payload["valid"] is False
    checks = {item["name"]: item for item in payload["checks"]}
    for name in (
        "mesh.graph",
        "mesh.partitions_dir",
        "static.invariant",
        "static.geovars",
        "static.keptvars",
        "static.tutorial_physics_files",
    ):
        assert checks[name]["status"] == "NOT_CONFIGURED"


def test_preflight_partition_name_follows_graph_basename(tmp_path: Path) -> None:
    config = _config(tmp_path)
    mesh = config["mesh"]  # type: ignore[index]
    graph = Path(str(mesh["graph"]))  # type: ignore[index]
    custom_graph = graph.with_name("custom.graph.info")
    graph.rename(custom_graph)
    mesh["graph"] = str(custom_graph)  # type: ignore[index]
    partitions = Path(str(mesh["partitions_dir"]))  # type: ignore[index]
    old_partition = partitions / "x1.test.graph.info.part.4"
    custom_partition = partitions / "custom.graph.info.part.4"
    old_partition.rename(custom_partition)

    payload = preflight_payload(config)

    assert payload["valid"] is True
    checks = {item["name"]: item for item in payload["checks"]}
    assert checks["mesh.partition"]["path"] == str(custom_partition)
    assert checks["mesh.partition"]["status"] == "OK"


def test_preflight_accepts_parent_of_spack_stack_checkout(tmp_path: Path) -> None:
    config = _config(tmp_path)
    variables = config["environment"]["variables"]  # type: ignore[index]
    checkout = Path(str(variables["STACK_ROOT"]))  # type: ignore[index]
    parent = checkout.parent
    variables["STACK_ROOT"] = str(parent)  # type: ignore[index]

    payload = preflight_payload(config)

    assert payload["valid"] is True
    checks = {item["name"]: item for item in payload["checks"]}
    assert checks["environment.variables.STACK_ROOT"]["path"] == str(checkout)
    assert checks["stack.site_setup"]["status"] == "OK"
    assert checks["stack.module_root"]["status"] == "OK"
