from __future__ import annotations

import json
from pathlib import Path

from bmatrix.cli import main


def _mpaswf_manifest(tmp_path: Path, count: int = 4) -> Path:
    rows = ["valid_time\tf048_state\tf024_state\tf048_restart\tf024_restart"]
    for index in range(count):
        f048 = tmp_path / f"mpasout.f048.{index}.nc"
        f024 = tmp_path / f"mpasout.f024.{index}.nc"
        r048 = tmp_path / f"restart.f048.{index}.nc"
        r024 = tmp_path / f"restart.f024.{index}.nc"
        for path in (f048, f024, r048, r024):
            path.write_bytes(b"non-empty")
        rows.append(
            f"2026-06-{22 + index:02d}T00:00:00Z\t{f048}\t{f024}\t{r048}\t{r024}"
        )
    manifest = tmp_path / "mpas-forecast-manifest.tsv"
    manifest.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return manifest


def test_check_manifest_cli_accepts_current_mpaswf_schema(tmp_path: Path, capsys) -> None:
    manifest = _mpaswf_manifest(tmp_path)

    rc = main(["check-manifest", "--manifest", str(manifest)])

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert rc == 0
    assert report["valid"] is True
    assert report["pair_count"] == 4
    assert report["pairs"][0]["f048"]["path"].endswith("mpasout.f048.0.nc")
    assert report["pairs"][0]["f024"]["path"].endswith("mpasout.f024.0.nc")


def test_check_manifest_cli_rejects_incomplete_campaign(tmp_path: Path, capsys) -> None:
    manifest = _mpaswf_manifest(tmp_path, count=3)

    rc = main(["check-manifest", "--manifest", str(manifest)])

    captured = capsys.readouterr()
    assert rc == 2
    assert "requires at least 4" in captured.err
