from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from bmatrix.nmc_core.checks import validate_manifest
from bmatrix.nmc_core.manifest import ManifestError


def _manifest(tmp_path: Path) -> Path:
    products = []
    for index in range(8):
        path = tmp_path / f"state-{index}.nc"
        path.write_bytes(b"netcdf-placeholder")
        products.append(path)
    manifest = tmp_path / "mpas-forecast-manifest.tsv"
    with manifest.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(["valid_time", "f048_state", "f024_state", "f048_restart", "f024_restart"])
        for index in range(4):
            writer.writerow([
                f"2018-04-{index + 1:02d}T00:00:00Z",
                products[index * 2],
                products[index * 2 + 1],
                "restart48.nc",
                "restart24.nc",
            ])
    return manifest


def _sidecar(manifest: Path) -> Path:
    path = manifest.with_suffix(".json")
    payload = {
        "schema_version": 1,
        "contract": "monan-nmc-forecast-pairs-v1",
        "producer": "mpaswf",
        "consumer": "MPAS-BMatrix",
        "manifest": manifest.name,
        "manifest_format": "tsv",
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "columns": ["valid_time", "f048_state", "f024_state", "f048_restart", "f024_restart"],
        "pair_count": 4,
        "pair_semantics": {},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_manifest_accepts_verified_mpaswf_contract(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    _sidecar(manifest)
    report = validate_manifest(manifest)
    assert report["producer_contract_verified"] is True
    assert report["producer_contract"]["contract"] == "monan-nmc-forecast-pairs-v1"


def test_manifest_rejects_sidecar_for_modified_tsv(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    _sidecar(manifest)
    manifest.write_text(manifest.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="SHA-256"):
        validate_manifest(manifest)


def test_legacy_manifest_without_sidecar_remains_supported(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    report = validate_manifest(manifest)
    assert report["producer_contract_verified"] is False
    assert report["producer_contract"] is None
