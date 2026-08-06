from __future__ import annotations

from bmatrix.dirac_core.config_files import _configured_points
from bmatrix.unbalance_core.config_files import _read_drivers


def test_dirac_points_keep_latitude_and_longitude_paired() -> None:
    latitudes, longitudes = _configured_points(
        {
            "points": [
                {"latitude": 30.0, "longitude": 130.0},
                {"latitude": -34.6, "longitude": -58.4},
            ]
        }
    )

    assert latitudes == [30.0, -34.6]
    assert longitudes == [130.0, -58.4]


def test_dirac_parallel_lists_remain_supported_for_legacy_contracts() -> None:
    latitudes, longitudes = _configured_points(
        {
            "latitudes": [30.0, -34.6],
            "longitudes": [130.0, -58.4],
        }
    )

    assert latitudes == [30.0, -34.6]
    assert longitudes == [130.0, -58.4]


def test_unbalance_drivers_have_validated_defaults_and_allow_explicit_override() -> None:
    assert _read_drivers({}) == {
        "read local sampling": True,
        "read global sampling": False,
        "read vertical balance": True,
    }
    assert _read_drivers({"drivers": {"read global sampling": True}}) == {
        "read local sampling": True,
        "read global sampling": True,
        "read vertical balance": True,
    }
