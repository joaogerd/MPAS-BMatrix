from __future__ import annotations

from pathlib import Path

import pytest

from bmatrix.bflow_core.manifest import read_manifest as read_bflow_manifest
from bmatrix.nmc_core.checks import validate_manifest
from bmatrix.nmc_core.manifest import ManifestError


def _write_manifest(tmp_path: Path, count: int) -> Path:
    rows = ["valid_time\tf048\tf024"]
    for hour in range(count):
        f048 = tmp_path / f"f048_{hour}.nc"
        f024 = tmp_path / f"f024_{hour}.nc"
        f048.write_bytes(b"f48")
        f024.write_bytes(b"f24")
        rows.append(f"2026-06-22T{hour:02d}:00:00Z\t{f048}\t{f024}")
    manifest = tmp_path / "bflow-manifest.tsv"
    manifest.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return manifest


def _write_mpaswf_manifest(tmp_path: Path, count: int) -> Path:
    rows = ["valid_time\tf048_state\tf024_state\tf048_restart\tf024_restart"]
    for hour in range(count):
        f048_state = tmp_path / f"mpasout_f048_{hour}.nc"
        f024_state = tmp_path / f"mpasout_f024_{hour}.nc"
        f048_restart = tmp_path / f"restart_f048_{hour}.nc"
        f024_restart = tmp_path / f"restart_f024_{hour}.nc"
        for path, payload in (
            (f048_state, b"f48-state"),
            (f024_state, b"f24-state"),
            (f048_restart, b"f48-restart"),
            (f024_restart, b"f24-restart"),
        ):
            path.write_bytes(payload)
        rows.append(
            f"2026-06-22T{hour:02d}:00:00Z\t{f048_state}\t{f024_state}\t{f048_restart}\t{f024_restart}"
        )
    manifest = tmp_path / "mpas-forecast-manifest.tsv"
    manifest.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return manifest


def test_manifest_requires_four_complete_pairs_and_normalizes_iso_time(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, 4)

    report = validate_manifest(manifest)
    bflow_pairs = read_bflow_manifest(manifest)

    assert report["valid"] is True
    assert report["pair_count"] == 4
    assert bflow_pairs[0].valid_time == "2026-06-22_00:00:00"


def test_current_mpaswf_manifest_uses_da_state_columns(tmp_path: Path) -> None:
    manifest = _write_mpaswf_manifest(tmp_path, 4)

    report = validate_manifest(manifest)
    bflow_pairs = read_bflow_manifest(manifest)

    assert report["valid"] is True
    assert report["pair_count"] == 4
    assert bflow_pairs[0].valid_time == "2026-06-22_00:00:00"
    assert bflow_pairs[0].f048.name == "mpasout_f048_0.nc"
    assert bflow_pairs[0].f024.name == "mpasout_f024_0.nc"
    assert "restart" not in bflow_pairs[0].f048.name
    assert "restart" not in bflow_pairs[0].f024.name


def test_manifest_rejects_too_few_pairs(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, 3)

    with pytest.raises(ManifestError, match="requires at least 4"):
        validate_manifest(manifest)


def test_manifest_rejects_unknown_pair_columns(tmp_path: Path) -> None:
    manifest = tmp_path / "bad.tsv"
    manifest.write_text("valid_time\tfoo\tbar\n2026-06-22T00:00:00Z\ta\tb\n", encoding="utf-8")

    with pytest.raises(ManifestError, match="f048_state"):
        read_bflow_manifest(manifest)
