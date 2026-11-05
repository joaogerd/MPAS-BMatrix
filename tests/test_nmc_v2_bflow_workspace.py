"""Versioned forecast leads survive BFLOW input staging and reload."""
from pathlib import Path

import pytest
from bmatrix.bflow_core.model import nmc_leads
from bmatrix.errors import ConfigurationError

from bmatrix.bflow_core.manifest import read_manifest, write_manifest
from bmatrix.bflow_core.model import BflowPair
from bmatrix.bflow_core.workspace import link_pair_inputs, validate_pairs


def test_v2_nmc_leads_survive_bflow_manifest_and_symlink_names(tmp_path: Path) -> None:
    pairs = []
    for day in range(1, 5):
        older = tmp_path / f"older-{day}.nc"
        newer = tmp_path / f"newer-{day}.nc"
        older.write_bytes(b"state from 36 hour forecast")
        newer.write_bytes(b"state from 12 hour forecast")
        pairs.append(BflowPair(
            f"2027-01-{day:02d}_00:00:00", older, newer,
            older_lead_hours=36, newer_lead_hours=12,
        ))
    validate_pairs(pairs)
    manifest = write_manifest(tmp_path / "manifest.tsv", pairs)
    assert "older_lead_hours" in manifest.read_text()
    reloaded = read_manifest(manifest)
    assert reloaded == pairs
    link_pair_inputs(tmp_path, reloaded)
    first = tmp_path / "inputs/2027010100"
    assert (first / "f036.nc").resolve() == pairs[0].older
    assert (first / "f012.nc").resolve() == pairs[0].newer
    assert not (first / "f048.nc").exists()
    assert "OLDER_LEAD_HOURS=36" in (first / "pair.env").read_text()


def test_v1_manifest_remains_byte_compatible(tmp_path: Path) -> None:
    older = tmp_path / "f048.nc"
    newer = tmp_path / "f024.nc"
    older.touch()
    newer.touch()
    manifest = write_manifest(tmp_path / "v1.tsv", [
        BflowPair("2027-01-01_00:00:00", older, newer)
    ])
    assert manifest.read_text().splitlines()[0] == "valid_time\tf048\tf024"
    assert read_manifest(manifest)[0].older_lead_hours == 48


@pytest.mark.parametrize("invalid", [12.5, True, "12", -1, 0, None])
def test_nmc_leads_cannot_be_silently_coerced_to_integer(invalid):
    case = {"bflow": {"nmc": {
        "older_lead_hours": 36, "newer_lead_hours": invalid
    }}}
    with pytest.raises(ConfigurationError, match="older_lead_hours"):
        nmc_leads(case)
