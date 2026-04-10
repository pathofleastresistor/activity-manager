"""Utility functions for Activity Manager."""
from __future__ import annotations

import logging

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


def dt_as_local(dt_str: str) -> str:
    """Parse an ISO datetime string and return it in local time as an ISO string."""
    parsed = dt_util.parse_datetime(dt_str)
    if parsed is None:
        raise ValueError(f"Cannot parse datetime string: {dt_str!r}")
    return dt_util.as_local(parsed).isoformat()


def duration_to_ms(frequency: dict | int) -> int:
    """Convert a frequency dict or legacy integer (days) to milliseconds."""
    try:
        return int(frequency) * 24 * 60 * 60 * 1000
    except (TypeError, ValueError):
        pass

    if not isinstance(frequency, dict):
        raise TypeError(f"Expected dict or int for frequency, got {type(frequency)!r}")

    ms = 0
    ms += frequency.get("days", 0) * 24 * 60 * 60 * 1000
    ms += frequency.get("hours", 0) * 60 * 60 * 1000
    ms += frequency.get("minutes", 0) * 60 * 1000
    ms += frequency.get("seconds", 0) * 1000
    return ms
