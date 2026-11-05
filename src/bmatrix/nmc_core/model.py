"""Time and record models for producer-supplied NMC manifests."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

TIME_FORMAT = "%Y-%m-%d_%H:%M:%S"
MINIMUM_PAIRS = 4


@dataclass(frozen=True)
class NMCManifestPair:
    """One same-valid-time NMC pair, including its actual lead durations.

    f048/f024 are retained as historical Python fields for legacy callers.
    The generic API and all v2 user messages use older/newer semantics.
    """

    valid_time: str
    f048: Path
    f024: Path
    older_lead_hours: int = 48
    newer_lead_hours: int = 24

    @property
    def older(self) -> Path:
        return self.f048

    @property
    def newer(self) -> Path:
        return self.f024

    @property
    def leads_hours(self) -> tuple[int, int]:
        return self.older_lead_hours, self.newer_lead_hours


def parse_time(value: str) -> datetime:
    """Accept legacy MPAS time strings and ISO-8601 producer timestamps."""
    try:
        return datetime.strptime(value, TIME_FORMAT)
    except ValueError:
        pass
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(
            f"Invalid NMC valid_time {value!r}; expected {TIME_FORMAT} or timezone-aware ISO-8601."
        ) from error
    if parsed.tzinfo is None:
        raise ValueError(
            f"ISO-8601 NMC valid_time {value!r} must include a UTC offset or trailing Z."
        )
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def normalize_time(value: str) -> str:
    """Return the legacy MPAS time spelling used in workspace names and logs."""
    return parse_time(value).strftime(TIME_FORMAT)
