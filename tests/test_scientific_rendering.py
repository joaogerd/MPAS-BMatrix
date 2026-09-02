from __future__ import annotations

import importlib
import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from bmatrix.dirac_core.checks import check as check_dirac
from bmatrix.dirac_core.config_files import write_dirac_yaml
from bmatrix.dirac_core.prepare import prepare as prepare_dirac
from bmatrix.bflow_core.netcdf_utils import CDF5_FORMAT
from bmatrix.hdiag_core.config_files import write_hdiag_yaml
from bmatrix.nicas_core.static import link_nicas_support
from bmatrix.so_core.checks import so_errors
from bmatrix.so_core.config_files import write_so_yaml
from bmatrix.so_core.static import create_so_background, link_so_support, validate_analysis_output
from bmatrix.vbal_core.config_files import write_vbal_yaml


CANONICAL_CONTROLS = [
    "air_horizontal_streamfunction",
    "air_horizontal_velocity_potential",
    "air_temperature",
    "water_vapor_mixing_ratio_wrt_moist_air",
    "air_pressure_at_surface",
]

FILE_ALIASES = [
    {"in code": "air_horizontal_streamfunction", "in file": "stream_function"},
    {"in code": "air_horizontal_velocity_potential", "in file": "velocity_potential"},
    {"in code": "air_temperature", "in file": "temperature"},
    {"in code": "water_vapor_mixing_ratio_wrt_moist_air", "in file": "spechum"},
    {"in code": "air_pressure_at_surface", "in file": "surface_pressure"},
]

COMPOSITE_ALIASES = [
    {
        "in code": "air_horizontal_streamfunction-air_horizontal_streamfunction",
        "in file": "stream_function-stream_function",
    },
    {
        "in code": "air_horizontal_streamfunction-water_vapor_mixing_ratio_wrt_moist_air",
        "in file": "stream_function-spechum",
    },
    {
        "in code": "water_vapor_mixing_ratio_wrt_moist_air-water_vapor_mixing_ratio_wrt_moist_air",
        "in file": "spechum-spechum",
    },
    {
        "in code": "air_horizontal_streamfunction-air_horizontal_velocity_potential",
        "in file": "stream_function-velocity_potential",
    },
    {
        "in code": "water_vapor_mixing_ratio_wrt_moist_air-air_horizontal_velocity_potential",
        "in file": "spechum-velocity_potential",
    },
    {
        "in code": "air_horizontal_velocity_potential-air_horizontal_velocity_potential",
        "in file": "velocity_potential-velocity_potential",
    },
    {"in code": "air_horizontal_streamfunction-air_temperature", "in file": "stream_function-temperature"},
    {
        "in code": "water_vapor_mixing_ratio_wrt_moist_air-air_temperature",
        "in file": "spechum-temperature",
    },
    {
        "in code": "air_horizontal_velocity_potential-air_temperature",
        "in file": "velocity_potential-temperature",
    },
    {"in code": "air_temperature-air_temperature", "in file": "temperature-temperature"},
    {
        "in code": "air_horizontal_streamfunction-air_pressure_at_surface",
        "in file": "stream_function-surface_pressure",
    },
    {
        "in code": "water_vapor_mixing_ratio_wrt_moist_air-air_pressure_at_surface",
        "in file": "spechum-surface_pressure",
    },
    {
        "in code": "air_horizontal_velocity_potential-air_pressure_at_surface",
        "in file": "velocity_potential-surface_pressure",
    },
    {
        "in code": "air_temperature-air_pressure_at_surface",
        "in file": "temperature-surface_pressure",
    },
    {
        "in code": "air_pressure_at_surface-air_pressure_at_surface",
        "in file": "surface_pressure-surface_pressure",
    },
]

ANALYSIS_VARIABLES = [
    "eastward_wind",
    "northward_wind",
    "air_temperature",
    "water_vapor_mixing_ratio_wrt_moist_air",
    "air_pressure_at_surface",
]

MPAS_ANALYSIS_VARIABLES = [
    "uReconstructZonal",
    "uReconstructMeridional",
    "theta",
    "qv",
    "surface_pressure",
]

MAIN_DIRAC_LATS = [
    30.31011691,
    26.56505123,
    35.68501691,
    19.01699038,
    19.44244244,
    31.21645245,
    -23.55867959,
    40.74997906,
    24.86999229,
    -34.60250161,
    28.6699929,
    55.75216412,
    41.10499615,
    23.72305971,
    30.04996035,
    37.5663491,
    22.4949693,
    39.92889223,
    -6.174417705,
    33.98997825,
    51.49999473,
    35.67194277,
]

MAIN_DIRAC_LONS = [
    130.11182691,
    -102.95294521,
    139.7514074,
    72.8569893,
    -99.1309882,
    121.4365047,
    -46.62501998,
    -73.98001693,
    66.99000891,
    -58.39753137,
    77.23000403,
    37.61552283,
    29.01000159,
    90.40857947,
    31.24996822,
    126.999731,
    88.32467566,
    116.3882857,
    106.8294376,
    -118.1799805,
    -0.116721844,
    51.42434403,
]

MAIN_FUNCTIONAL_DIRAC_KEYS = {"ndir", "dirLats", "dirLons", "ildir", "dirvar"}


def _config() -> dict[str, object]:
    return {
        "mesh": {"name": "x1.test", "nproc": 4},
        "project": {"work_root": "/workspace/work"},
        "install": {"root": "/workspace/install"},
        "bflow": {
            "products": {
                "template": "template.nc",
                "older_full": "older.nc",
                "newer_full": "newer.nc",
                "perturbation": "custom_ptb.nc",
            }
        },
        "controls": [
            {"code": "air_horizontal_streamfunction", "file": "stream_function", "dimensions": "3d"},
            {"code": "air_horizontal_velocity_potential", "file": "velocity_potential", "dimensions": "3d"},
            {"code": "air_temperature", "file": "temperature", "dimensions": "3d"},
            {"code": "water_vapor_mixing_ratio_wrt_moist_air", "file": "spechum", "dimensions": "3d"},
            {"code": "air_pressure_at_surface", "file": "surface_pressure", "dimensions": "2d"},
        ],
        "vbal": {
            "files_prefix": "mpas",
            "group_variable_order": [
                "air_horizontal_streamfunction",
                "water_vapor_mixing_ratio_wrt_moist_air",
                "air_horizontal_velocity_potential",
                "air_temperature",
                "air_pressure_at_surface",
            ],
            "relations": [
                {
                    "balanced_variable": "air_horizontal_velocity_potential",
                    "unbalanced_variable": "air_horizontal_streamfunction",
                    "diagonal_regression": True,
                },
                {"balanced_variable": "air_temperature", "unbalanced_variable": "air_horizontal_streamfunction"},
                {
                    "balanced_variable": "air_pressure_at_surface",
                    "unbalanced_variable": "air_horizontal_streamfunction",
                },
            ],
            "drivers": {},
            "sampling": {},
        },
        "hdiag": {
            "files_prefix": "mpas",
            "drivers": {},
            "sampling": {},
            "variance": {
                "initial_length_scales": [
                    {
                        "variables": ["air_horizontal_streamfunction", "air_temperature"],
                        "value": 1000000.0,
                    }
                ]
            },
            "fit": {},
        },
        "nicas": {"files_prefix": "mpas", "drivers": {"multivariate strategy": "univariate"}},
        "dirac": {
            "ndir": 1,
            "index": 10,
            "variable": "air_temperature",
            "latitudes": MAIN_DIRAC_LATS,
            "longitudes": MAIN_DIRAC_LONS,
            "background_variables": [
                *ANALYSIS_VARIABLES,
                "air_pressure",
                "u",
                "rho",
                "theta",
                "pressure_p",
            ],
        },
        "single_observation": {
            "window_hours_before_analysis": 3,
            "window_hours": 6,
            "minimizer": "DRPCG",
            "ninner": 1,
            "gradient_norm_reduction": 0.1,
            "analysis_variables": ANALYSIS_VARIABLES,
            "background_variables": [
                *ANALYSIS_VARIABLES,
                "air_pressure",
                "spechum",
                "surface_pressure",
                "temperature",
                "uReconstructMeridional",
                "uReconstructZonal",
                "theta",
                "rho",
                "u",
                "qv",
                "pressure",
                "pressure_p",
            ],
            "variants": {"default": ["temperature"]},
            "observations": {
                "temperature": {
                    "name": "SO_T",
                    "simulated_variable": "airTemperature",
                    "latitude": 0.0,
                    "longitude": 0.0,
                    "pressure": 80000.0,
                    "error": 1.0,
                    "value": 280.0,
                    "output_file": "obsout.h5",
                }
            },
        },
    }


def test_renderers_use_declared_product_names_and_control_mapping(tmp_path: Path) -> None:
    config = _config()
    vbal_path = tmp_path / "vbal.yaml"
    hdiag_path = tmp_path / "hdiag.yaml"

    write_vbal_yaml(config, vbal_path, nmembers=4, date="2026-06-10T00:00:00Z")
    write_hdiag_yaml(config, hdiag_path, nmembers=4, date="2026-06-10T00:00:00Z")

    vbal = yaml.safe_load(vbal_path.read_text())
    hdiag = yaml.safe_load(hdiag_path.read_text())
    ensemble = vbal["background error"]["ensemble"]["members from template"]["template"]
    assert ensemble["state variables"] == [
        "stream_function",
        "spechum",
        "velocity_potential",
        "temperature",
        "surface_pressure",
    ]
    assert ensemble["filename"] == "../samples/custom_ptb_%mem%.nc"
    assert "output ensemble" not in vbal["background error"]
    relation = vbal["background error"]["saber outer blocks"][0]["calibration"]["vertical balance"]["vbal"][0]
    assert relation == {
        "balanced variable": "velocity_potential",
        "unbalanced variable": "stream_function",
        "diagonal regression": True,
    }

    scale = hdiag["background error"]["saber central block"]["calibration"]["variance"]["initial length-scale"][0]
    assert scale["variables"] == ["stream_function", "temperature"]
    hdiag_ensemble = hdiag["background error"]["ensemble"]["members from template"]["template"]
    assert hdiag_ensemble["filename"] == "../samples/custom_ptb_%mem%.nc"
    hdiag_vbal = hdiag["background error"]["saber outer blocks"][0]
    assert hdiag_vbal["saber block name"] == "BUMP_VerticalBalance"
    assert hdiag_vbal["read"]["io"] == {"data directory": "../vbal", "files prefix": "mpas"}
    assert hdiag_vbal["read"]["drivers"] == {
        "read local sampling": True,
        "read vertical balance": True,
    }
    assert hdiag_vbal["read"]["vertical balance"]["vbal"][0] == relation


def test_so_renderer_uses_normalized_vbal_relations(tmp_path: Path) -> None:
    config = _config()
    path = tmp_path / "so.yaml"
    write_so_yaml(
        config,
        path,
        date="2026-06-10T00:00:00Z",
        nicas_dir=tmp_path / "nicas",
        stddev_file=tmp_path / "stddev.nc",
        vbal_dir=tmp_path / "vbal",
    )
    rendered = yaml.safe_load(path.read_text())
    relations = rendered["cost function"]["background error"]["saber outer blocks"][1]["read"]["vertical balance"]["vbal"]
    assert relations == [
        {
            "balanced variable": "air_horizontal_velocity_potential",
            "unbalanced variable": "air_horizontal_streamfunction",
            "diagonal regression": True,
        },
        {"balanced variable": "air_temperature", "unbalanced variable": "air_horizontal_streamfunction"},
        {
            "balanced variable": "air_pressure_at_surface",
            "unbalanced variable": "air_horizontal_streamfunction",
        },
    ]


def test_so_renderer_splits_nicas_read_grids_by_vertical_dimension(tmp_path: Path) -> None:
    config = _config()
    path = tmp_path / "so.yaml"
    write_so_yaml(
        config,
        path,
        date="2026-06-10T00:00:00Z",
        nicas_dir=tmp_path / "nicas",
        stddev_file=tmp_path / "stddev.nc",
        vbal_dir=tmp_path / "vbal",
    )
    rendered = yaml.safe_load(path.read_text())
    read = rendered["cost function"]["background error"]["saber central block"]["read"]
    assert read["grids"] == [
        {
            "model": {
                "variables": [
                    "air_horizontal_streamfunction",
                    "air_horizontal_velocity_potential",
                    "air_temperature",
                    "water_vapor_mixing_ratio_wrt_moist_air",
                ]
            }
        },
        {"model": {"variables": ["air_pressure_at_surface"]}},
    ]
    assert rendered["cost function"]["background error"]["saber central block"]["active variables"] == [
        "air_horizontal_streamfunction",
        "air_horizontal_velocity_potential",
        "air_temperature",
        "water_vapor_mixing_ratio_wrt_moist_air",
        "air_pressure_at_surface",
    ]
    assert "same horizontal convolution" not in read


def _bump_nicas_so(rendered: dict[str, object]) -> dict[str, object]:
    return rendered["cost function"]["background error"]["saber central block"]


def _bump_vbal_so(rendered: dict[str, object]) -> dict[str, object]:
    return rendered["cost function"]["background error"]["saber outer blocks"][1]


def _assert_application_uses_canonical_controls(rendered: dict[str, object], background_error: dict[str, object]) -> None:
    nicas = background_error["saber central block"]
    vbal = background_error["saber outer blocks"][1]
    linear = background_error["linear variable change"]
    assert nicas["active variables"] == CANONICAL_CONTROLS
    assert nicas["read"]["io"]["alias"] == FILE_ALIASES
    assert nicas["read"]["grids"] == [
        {"model": {"variables": CANONICAL_CONTROLS[:4]}},
        {"model": {"variables": ["air_pressure_at_surface"]}},
    ]
    assert vbal["read"]["io"]["alias"] == FILE_ALIASES + COMPOSITE_ALIASES
    assert vbal["read"]["model"] == {"nearest 3d level": "bottom"}
    assert vbal["read"]["vertical balance"]["vbal"] == [
        {
            "balanced variable": "air_horizontal_velocity_potential",
            "unbalanced variable": "air_horizontal_streamfunction",
            "diagonal regression": True,
        },
        {"balanced variable": "air_temperature", "unbalanced variable": "air_horizontal_streamfunction"},
        {
            "balanced variable": "air_pressure_at_surface",
            "unbalanced variable": "air_horizontal_streamfunction",
        },
    ]
    assert linear["input variables"] == CANONICAL_CONTROLS
    assert linear["output variables"] == [
        *ANALYSIS_VARIABLES,
    ]
    assert rendered["geometry"]["alias"] == FILE_ALIASES


def _assert_no_file_names_in_control_slots(background_error: dict[str, object]) -> None:
    old_names = {"stream_function", "velocity_potential", "temperature", "spechum", "surface_pressure"}
    nicas = background_error["saber central block"]
    vbal = background_error["saber outer blocks"][1]
    linear = background_error["linear variable change"]
    slots = [
        nicas["active variables"],
        linear["input variables"],
        *(grid["model"]["variables"] for grid in nicas["read"]["grids"]),
    ]
    for relation in vbal["read"]["vertical balance"]["vbal"]:
        slots.append([relation["balanced variable"], relation["unbalanced variable"]])
    for slot in slots:
        assert old_names.isdisjoint(slot)


def test_so_renderer_uses_canonical_controls_and_aliases(tmp_path: Path) -> None:
    config = _config()
    path = tmp_path / "so.yaml"
    write_so_yaml(
        config,
        path,
        date="2026-06-10T00:00:00Z",
        nicas_dir=tmp_path / "nicas",
        stddev_file=tmp_path / "stddev.nc",
        vbal_dir=tmp_path / "vbal",
    )
    rendered = yaml.safe_load(path.read_text())
    background_error = rendered["cost function"]["background error"]
    _assert_application_uses_canonical_controls(rendered["cost function"], background_error)
    _assert_no_file_names_in_control_slots(background_error)
    assert set(ANALYSIS_VARIABLES).issubset(rendered["cost function"]["background"]["state variables"])
    assert "water_vapor_mixing_ratio_wrt_moist_air" in rendered["cost function"]["background"]["state variables"]
    stddev = background_error["saber outer blocks"][0]["read"]["model file"]
    assert "alias" not in stddev


def test_dirac_renderer_uses_complete_b_inputs_and_declared_impulse(tmp_path: Path) -> None:
    config = _config()
    path = tmp_path / "dirac.yaml"
    write_dirac_yaml(
        config,
        path,
        date="2026-06-10T00:00:00Z",
        nicas_dir=tmp_path / "nicas",
        stddev_file=tmp_path / "stddev.nc",
        vbal_dir=tmp_path / "vbal",
    )
    rendered = yaml.safe_load(path.read_text())
    output = rendered["output dirac"]
    assert output == {
        "filename": "./mpas.dirac.nc",
        "date": "2026-06-10T00:00:00Z",
        "stream name": "control",
    }
    assert rendered["dirac"] == {
        "ndir": 1,
        "dirLats": MAIN_DIRAC_LATS,
        "dirLons": MAIN_DIRAC_LONS,
        "ildir": 10,
        "dirvar": "air_temperature",
    }
    assert set(rendered["dirac"]) == MAIN_FUNCTIONAL_DIRAC_KEYS
    assert {"dirLevs", "dirVars"}.isdisjoint(rendered["dirac"])
    assert {"ndir", "ildir", "dirvar", "dirlat", "dirlon", "dirLats", "dirLons"}.isdisjoint(output)
    assert rendered["background error"]["linear variable change"]["input variables"] == [
        "air_horizontal_streamfunction",
        "air_horizontal_velocity_potential",
        "air_temperature",
        "water_vapor_mixing_ratio_wrt_moist_air",
        "air_pressure_at_surface",
    ]
    assert set(ANALYSIS_VARIABLES).issubset(rendered["background"]["state variables"])


def test_dirac_contract_matches_functional_main_shape_except_canonical_variable(tmp_path: Path) -> None:
    config = _config()
    path = tmp_path / "dirac.yaml"
    write_dirac_yaml(
        config,
        path,
        date="2026-06-10T00:00:00Z",
        nicas_dir=tmp_path / "nicas",
        stddev_file=tmp_path / "stddev.nc",
        vbal_dir=tmp_path / "vbal",
    )

    rendered = yaml.safe_load(path.read_text())
    functional_main_dirac = {
        "ndir": 1,
        "dirLats": MAIN_DIRAC_LATS,
        "dirLons": MAIN_DIRAC_LONS,
        "ildir": 10,
        "dirvar": "temperature",
    }

    assert set(rendered["dirac"]) == set(functional_main_dirac)
    assert rendered["dirac"] | {"dirvar": "temperature"} == functional_main_dirac
    assert rendered["dirac"]["dirvar"] == "air_temperature"


def test_dirac_renderer_uses_canonical_controls_and_aliases(tmp_path: Path) -> None:
    config = _config()
    path = tmp_path / "dirac.yaml"
    write_dirac_yaml(
        config,
        path,
        date="2026-06-10T00:00:00Z",
        nicas_dir=tmp_path / "nicas",
        stddev_file=tmp_path / "stddev.nc",
        vbal_dir=tmp_path / "vbal",
    )
    rendered = yaml.safe_load(path.read_text())
    _assert_application_uses_canonical_controls(rendered, rendered["background error"])
    _assert_no_file_names_in_control_slots(rendered["background error"])
    assert "water_vapor_mixing_ratio_wrt_moist_air" in rendered["background"]["state variables"]
    stddev = rendered["background error"]["saber outer blocks"][0]["read"]["model file"]
    assert "alias" not in stddev


def test_dirac_renderer_uses_same_nicas_grid_split_as_so(tmp_path: Path) -> None:
    config = _config()
    so_path = tmp_path / "so.yaml"
    dirac_path = tmp_path / "dirac.yaml"
    kwargs = {
        "date": "2026-06-10T00:00:00Z",
        "nicas_dir": tmp_path / "nicas",
        "stddev_file": tmp_path / "stddev.nc",
        "vbal_dir": tmp_path / "vbal",
    }
    write_so_yaml(config, so_path, **kwargs)
    write_dirac_yaml(config, dirac_path, **kwargs)

    so_rendered = yaml.safe_load(so_path.read_text())
    dirac_rendered = yaml.safe_load(dirac_path.read_text())
    so_read = so_rendered["cost function"]["background error"]["saber central block"]["read"]
    dirac_read = dirac_rendered["background error"]["saber central block"]["read"]
    assert dirac_read["grids"] == so_read["grids"]
    assert len(dirac_read["grids"]) == 2


def test_nicas_grid_split_requires_2d_and_3d_controls(tmp_path: Path) -> None:
    config = _config()
    config["controls"] = [
        {"code": "air_horizontal_streamfunction", "file": "stream_function", "dimensions": "3d"},
        {"code": "air_temperature", "file": "temperature", "dimensions": "3d"},
    ]
    config["vbal"]["group_variable_order"] = ["air_horizontal_streamfunction", "air_temperature"]
    config["vbal"]["relations"] = [
        {"balanced_variable": "air_temperature", "unbalanced_variable": "air_horizontal_streamfunction"}
    ]
    path = tmp_path / "so.yaml"
    try:
        write_so_yaml(
            config,
            path,
            date="2026-06-10T00:00:00Z",
            nicas_dir=tmp_path / "nicas",
            stddev_file=tmp_path / "stddev.nc",
            vbal_dir=tmp_path / "vbal",
        )
    except ValueError as exc:
        assert "grids separados" in str(exc)
    else:
        raise AssertionError("SO deveria rejeitar leitura NICAS sem divisão 3D/2D.")


def test_so_renderer_rejects_background_missing_control2analysis_output(tmp_path: Path) -> None:
    config = _config()
    config["single_observation"]["background_variables"] = [
        variable for variable in ANALYSIS_VARIABLES if variable != "water_vapor_mixing_ratio_wrt_moist_air"
    ]
    with pytest.raises(ValueError, match="water_vapor_mixing_ratio_wrt_moist_air"):
        write_so_yaml(
            config,
            tmp_path / "so.yaml",
            date="2026-06-10T00:00:00Z",
            nicas_dir=tmp_path / "nicas",
            stddev_file=tmp_path / "stddev.nc",
            vbal_dir=tmp_path / "vbal",
        )


def test_dirac_renderer_rejects_background_missing_control2analysis_output(tmp_path: Path) -> None:
    config = _config()
    config["dirac"]["background_variables"] = [
        variable for variable in ANALYSIS_VARIABLES if variable != "water_vapor_mixing_ratio_wrt_moist_air"
    ]
    with pytest.raises(ValueError, match="water_vapor_mixing_ratio_wrt_moist_air"):
        write_dirac_yaml(
            config,
            tmp_path / "dirac.yaml",
            date="2026-06-10T00:00:00Z",
            nicas_dir=tmp_path / "nicas",
            stddev_file=tmp_path / "stddev.nc",
            vbal_dir=tmp_path / "vbal",
        )


def test_mpas_analysis_stream_remains_native_not_canonical() -> None:
    assert set(ANALYSIS_VARIABLES).isdisjoint(MPAS_ANALYSIS_VARIABLES)
    assert MPAS_ANALYSIS_VARIABLES == [
        "uReconstructZonal",
        "uReconstructMeridional",
        "theta",
        "qv",
        "surface_pressure",
    ]


def test_so_and_dirac_renderers_do_not_render_stream_lists(tmp_path: Path) -> None:
    config = _config()
    so_path = tmp_path / "so.yaml"
    dirac_path = tmp_path / "dirac.yaml"
    kwargs = {
        "date": "2026-06-10T00:00:00Z",
        "nicas_dir": tmp_path / "nicas",
        "stddev_file": tmp_path / "stddev.nc",
        "vbal_dir": tmp_path / "vbal",
    }

    write_so_yaml(config, so_path, **kwargs)
    write_dirac_yaml(config, dirac_path, **kwargs)

    assert "stream_list.atmosphere.analysis" not in so_path.read_text()
    assert "stream_list.atmosphere.analysis" not in dirac_path.read_text()


def _hdiag_static_files(path: Path, stream_text: str) -> None:
    path.mkdir(parents=True)
    for name in ["bg.nc", "namelist.atmosphere_240km", "streams.atmosphere_240km", "templateFields.240km.nc"]:
        (path / name).write_text(name)
    (path / "stream_list.atmosphere.analysis").write_text(stream_text)


def test_so_support_preserves_inherited_analysis_stream_list(tmp_path: Path) -> None:
    inherited = "compatible_registry_field\n"
    hdiag_run = tmp_path / "hdiag" / "HDIAG"
    run_dir = tmp_path / "SO"
    run_dir.mkdir()
    _hdiag_static_files(hdiag_run, inherited)

    link_so_support(hdiag_run, run_dir)

    stream_list = run_dir / "stream_list.atmosphere.analysis"
    assert stream_list.is_symlink()
    assert stream_list.read_text() == inherited
    assert stream_list.read_text().splitlines() != MPAS_ANALYSIS_VARIABLES
    assert set(ANALYSIS_VARIABLES).isdisjoint(stream_list.read_text().splitlines())


def test_dirac_support_preserves_inherited_analysis_stream_list(tmp_path: Path) -> None:
    inherited = "compatible_registry_field\n"
    hdiag_run = tmp_path / "hdiag" / "HDIAG"
    run_dir = tmp_path / "DIRAC"
    run_dir.mkdir()
    _hdiag_static_files(hdiag_run, inherited)

    link_nicas_support(hdiag_run, run_dir)

    stream_list = run_dir / "stream_list.atmosphere.analysis"
    assert stream_list.is_symlink()
    assert stream_list.read_text() == inherited
    assert stream_list.read_text().splitlines() != MPAS_ANALYSIS_VARIABLES
    assert set(ANALYSIS_VARIABLES).isdisjoint(stream_list.read_text().splitlines())


def _dirac_prepare_config(tmp_path: Path) -> dict[str, object]:
    config = _config()
    install = tmp_path / "install"
    (install / "bin").mkdir(parents=True)
    (install / "bin" / "mpasjedi_error_covariance_toolbox.x").write_text("toolbox")
    config["install"] = {"root": str(install)}
    config["project"] = {"work_root": str(tmp_path / "work"), "project_root": str(tmp_path / "project")}
    config["environment"] = {"loader": "load-env.sh"}
    config["dirac"]["background_variables"] = [
        *ANALYSIS_VARIABLES,
        "air_pressure",
    ]
    return config


def _dirac_prepare_workspaces(tmp_path: Path) -> tuple[Path, Path, Path]:
    nicas = tmp_path / "NICAS"
    hdiag = tmp_path / "HDIAG_ROOT"
    vbal = tmp_path / "VBAL_ROOT"
    for path in [
        nicas / "merge" / "mpas_nicas.nc",
        hdiag / "HDIAG" / "mpas.stddev.nc",
        vbal / "VBAL" / "mpas_vbal.nc",
        vbal / "VBAL" / "mpas_sampling.nc",
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("product")
    hdiag_run = hdiag / "HDIAG"
    for name in ["bg.nc", "namelist.atmosphere_240km", "streams.atmosphere_240km"]:
        (hdiag_run / name).write_text(name)
    (hdiag_run / "run_hdiag.yaml").write_text("date: 2026-06-22T00:00:00Z\n")
    (hdiag_run / "stream_list.atmosphere.analysis").write_text("compatible_registry_field\n")
    netcdf4 = pytest.importorskip("netCDF4")
    with netcdf4.Dataset(hdiag_run / "templateFields.240km.nc", "w", format=CDF5_FORMAT) as dataset:
        dataset.createDimension("Time", 1)
        dataset.createDimension("nCells", 1)
        for name in [*ANALYSIS_VARIABLES, "air_pressure"]:
            dataset.createVariable(name, "f4", ("Time", "nCells"))[:] = 1.0
    return nicas, hdiag, vbal


def test_dirac_prepare_does_not_require_so_native_variables_in_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dirac_prepare = importlib.import_module("bmatrix.dirac_core.prepare")

    monkeypatch.setattr(dirac_prepare, "validate_nicas", lambda _: True)
    monkeypatch.setattr(dirac_prepare, "validate_hdiag", lambda _: True)
    monkeypatch.setattr(dirac_prepare, "validate_vbal", lambda _: True)
    config = _dirac_prepare_config(tmp_path)
    nicas, hdiag, vbal = _dirac_prepare_workspaces(tmp_path)

    output = prepare_dirac(config, nicas, hdiag, vbal, workspace=tmp_path / "DIRAC")

    assert (output / "run_dirac.yaml").is_file()
    assert (output / "qsub_dirac.bash").is_file()
    assert not (output / "an.2026-06-22_00.00.00.nc").exists()
    assert not (output / "obsout_SO_T.h5").exists()
    assert not (output / "obsout_SO_U.h5").exists()
    assert "CostFunction::addIncrement: Analysis" not in (output / "run_dirac.yaml").read_text()
    assert (output / "stream_list.atmosphere.analysis").is_symlink()
    assert (output / "stream_list.atmosphere.analysis").read_text() == "compatible_registry_field\n"
    assert (output / "stream_list.atmosphere.analysis").read_text().splitlines() != MPAS_ANALYSIS_VARIABLES
    manifest = json.loads((output / "stage-manifest.json").read_text())
    assert manifest["outputs"]["dirac"] == str((output / "mpas.dirac.nc").resolve())


def _dirac_success_runlog(path: Path) -> None:
    (path / "run_dirac.runlog").write_text("Run: Finishing oops::ErrorCovarianceToolbox<MPAS> with status = 0\n")


def test_dirac_validation_accepts_expected_netcdf_product(tmp_path: Path) -> None:
    netcdf4 = pytest.importorskip("netCDF4")
    _dirac_success_runlog(tmp_path)
    with netcdf4.Dataset(tmp_path / "mpas.dirac.nc", "w", format=CDF5_FORMAT) as dataset:
        dataset.createDimension("x", 1)
        dataset.createVariable("air_temperature", "f4", ("x",))[:] = 1.0

    assert check_dirac(tmp_path)


def test_dirac_validation_rejects_missing_or_invalid_expected_product(tmp_path: Path) -> None:
    _dirac_success_runlog(tmp_path)

    with pytest.raises(RuntimeError, match="produto DIRAC ausente: mpas.dirac.nc"):
        check_dirac(tmp_path)

    (tmp_path / "mpas.dirac.nc").write_text("not netcdf")
    with pytest.raises(RuntimeError, match="não é NetCDF válido"):
        check_dirac(tmp_path)


def _native_analysis_file(path: Path, variables: list[str] | None = None) -> None:
    netcdf4 = pytest.importorskip("netCDF4")
    with netcdf4.Dataset(path, "w", format=CDF5_FORMAT) as dataset:
        dataset.createDimension("Time", 1)
        dataset.createDimension("nCells", 1)
        for name in variables or MPAS_ANALYSIS_VARIABLES:
            dataset.createVariable(name, "f4", ("Time", "nCells"))[:] = 0.0


def test_validate_analysis_output_accepts_mpas_native_file(tmp_path: Path) -> None:
    path = tmp_path / "an.2026-06-22_00.00.00.nc"
    _native_analysis_file(path)

    assert validate_analysis_output(path, MPAS_ANALYSIS_VARIABLES)


def test_validate_analysis_output_rejects_missing_native_fields(tmp_path: Path) -> None:
    path = tmp_path / "an.2026-06-22_00.00.00.nc"
    _native_analysis_file(path, ["uReconstructZonal", "theta"])

    with pytest.raises(RuntimeError, match="variáveis nativas esperadas"):
        validate_analysis_output(path, MPAS_ANALYSIS_VARIABLES)


def test_so_validation_accepts_native_analysis_output_with_analysis_log(tmp_path: Path) -> None:
    (tmp_path / "run_SO.runlog").write_text(
        "CostFunction::addIncrement: Analysis:\nRun: Finishing test with status = 0\n"
    )
    (tmp_path / "stdout.log").write_text("")
    (tmp_path / "stderr.log").write_text("")
    (tmp_path / "obsout_SO_T.h5").write_text("ok")
    (tmp_path / "obsout_SO_U.h5").write_text("ok")
    _native_analysis_file(tmp_path / "an.2026-06-22_00.00.00.nc")

    assert so_errors(tmp_path) == []


def _valid_so_outputs(path: Path) -> None:
    (path / "run_SO.runlog").write_text(
        "CostFunction::addIncrement: Analysis:\nRun: Finishing test with status = 0\n"
    )
    (path / "stdout.log").write_text("")
    (path / "stderr.log").write_text("")
    (path / "obsout_SO_T.h5").write_text("ok")
    (path / "obsout_SO_U.h5").write_text("ok")
    _native_analysis_file(path / "an.2026-06-22_00.00.00.nc")


def test_so_validation_fails_without_final_status_zero(tmp_path: Path) -> None:
    _valid_so_outputs(tmp_path)
    (tmp_path / "run_SO.runlog").write_text("CostFunction::addIncrement: Analysis:\n")

    errors = so_errors(tmp_path)

    assert any("status final de sucesso ausente" in error for error in errors)


def test_so_validation_fails_without_addincrement_analysis(tmp_path: Path) -> None:
    (tmp_path / "run_SO.runlog").write_text("Run: Finishing test with status = 0\n")
    (tmp_path / "stdout.log").write_text("")
    (tmp_path / "stderr.log").write_text("")
    (tmp_path / "obsout_SO_T.h5").write_text("ok")
    (tmp_path / "obsout_SO_U.h5").write_text("ok")
    _native_analysis_file(tmp_path / "an.2026-06-22_00.00.00.nc")

    errors = so_errors(tmp_path)

    assert any("não chegou em Analysis" in error for error in errors)


def test_so_validation_fails_without_analysis_file(tmp_path: Path) -> None:
    _valid_so_outputs(tmp_path)
    for path in tmp_path.glob("an.*.nc"):
        path.unlink()

    errors = so_errors(tmp_path)

    assert any("arquivo de análise an.*.nc ausente" in error for error in errors)


def test_so_validation_fails_when_analysis_file_is_not_cdf5(tmp_path: Path) -> None:
    netcdf4 = pytest.importorskip("netCDF4")
    _valid_so_outputs(tmp_path)
    path = next(tmp_path.glob("an.*.nc"))
    path.unlink()
    with netcdf4.Dataset(path, "w", format="NETCDF4") as dataset:
        dataset.createDimension("Time", 1)
        dataset.createDimension("nCells", 1)
        for name in MPAS_ANALYSIS_VARIABLES:
            dataset.createVariable(name, "f4", ("Time", "nCells"))[:] = 0.0

    errors = so_errors(tmp_path)

    assert any("não está em CDF5" in error for error in errors)


def test_so_validation_fails_when_native_analysis_fields_are_missing(tmp_path: Path) -> None:
    _valid_so_outputs(tmp_path)
    path = next(tmp_path.glob("an.*.nc"))
    path.unlink()
    _native_analysis_file(path, ["uReconstructZonal", "uReconstructMeridional"])

    errors = so_errors(tmp_path)

    assert any("variáveis nativas esperadas" in error for error in errors)


def test_so_validation_ignores_nonfatal_requested_field_messages(tmp_path: Path) -> None:
    _valid_so_outputs(tmp_path)
    (tmp_path / "stdout.log").write_text(
        "Requested field foo is deactivated due to packages, or is a scratch variable.\n"
    )

    assert so_errors(tmp_path) == []


def test_so_validation_fails_on_fatal_requested_field_messages(tmp_path: Path) -> None:
    _valid_so_outputs(tmp_path)
    (tmp_path / "stderr.log").write_text("ERROR: Requested field eastward_wind not available\n")

    errors = so_errors(tmp_path)

    assert any("ERROR: Requested field" in error for error in errors)


def test_so_validation_fails_on_qv_stream_parser_error(tmp_path: Path) -> None:
    _valid_so_outputs(tmp_path)
    (tmp_path / "stderr.log").write_text(
        "ERROR: Requested field qv not available\n"
        "CRITICAL ERROR: xml stream parser failed: ./streams.atmosphere_240km\n"
    )

    errors = so_errors(tmp_path)

    assert any("ERROR: Requested field" in error for error in errors)


def _minimal_so_template(path: Path, *, humidity_name: str) -> None:
    netcdf4 = pytest.importorskip("netCDF4")
    with netcdf4.Dataset(path, "w") as dataset:
        dataset.createDimension("Time", 1)
        dataset.createDimension("nCells", 2)
        dataset.createDimension("nVertLevels", 2)
        dataset.createDimension("nEdges", 3)
        dims_3d = ("Time", "nCells", "nVertLevels")
        edge_dims = ("Time", "nEdges", "nVertLevels")
        for name, value in {
            "pressure_base": 90000.0,
            "pressure_p": 1000.0,
            "theta": 300.0,
            "surface_pressure": 95000.0,
        }.items():
            dims = ("Time", "nCells") if name == "surface_pressure" else dims_3d
            variable = dataset.createVariable(name, "f4", dims)
            variable[:] = value
        qv = dataset.createVariable(humidity_name, "f4", dims_3d)
        qv[:] = np.array([[[0.01, 0.02], [0.03, 0.04]]], dtype="f4")
        dataset.createVariable("u", "f4", edge_dims)[:] = 0.0
        dataset.createVariable("rho", "f4", dims_3d)[:] = 1.0
        dataset.createVariable("uReconstructZonal", "f4", dims_3d)[:] = 2.0
        dataset.createVariable("uReconstructMeridional", "f4", dims_3d)[:] = 3.0


def test_create_so_background_copies_moist_air_specific_humidity_from_spechum(tmp_path: Path) -> None:
    netcdf4 = pytest.importorskip("netCDF4")
    source = tmp_path / "source.nc"
    output = tmp_path / "bg_so.nc"
    _minimal_so_template(source, humidity_name="spechum")

    create_so_background(source, output, ["water_vapor_mixing_ratio_wrt_moist_air"])

    with netcdf4.Dataset(output) as dataset:
        assert "spechum" in dataset.variables
        assert "water_vapor_mixing_ratio_wrt_moist_air" in dataset.variables
        np.testing.assert_allclose(
            dataset.variables["water_vapor_mixing_ratio_wrt_moist_air"][:],
            dataset.variables["spechum"][:],
        )


def test_create_so_background_derives_moist_air_specific_humidity_from_qv(tmp_path: Path) -> None:
    netcdf4 = pytest.importorskip("netCDF4")
    source = tmp_path / "source.nc"
    output = tmp_path / "bg_so.nc"
    _minimal_so_template(source, humidity_name="qv")

    create_so_background(source, output, ["water_vapor_mixing_ratio_wrt_moist_air"])

    with netcdf4.Dataset(output) as dataset:
        qv = dataset.variables["qv"][:]
        assert "water_vapor_mixing_ratio_wrt_moist_air" in dataset.variables
        np.testing.assert_allclose(
            dataset.variables["water_vapor_mixing_ratio_wrt_moist_air"][:],
            qv / (1.0 + qv),
        )
