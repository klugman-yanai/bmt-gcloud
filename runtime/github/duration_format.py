"""Human-readable duration strings shared by Check Run markdown helpers."""

from __future__ import annotations


def format_duration_seconds(seconds: int | None) -> str:
    """Format duration for display (e.g. ``2m 15s``). ``None`` maps to an em dash."""
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        minutes = seconds // 60
        remainder = seconds % 60
        return f"{minutes}m {remainder}s"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}h {minutes}m"


def floor_duration_for_check_summary(seconds: int, *, bucket_sec: int) -> int:
    """Snap wall seconds down so displayed elapsed/ETA match publish cadence."""
    if bucket_sec > 0:
        return max(0, (seconds // bucket_sec) * bucket_sec)
    if seconds >= 60:
        return (seconds // 60) * 60
    return 0


def format_duration_seconds_coarse(seconds: int | None) -> str:
    """Format elapsed/ETA in the in-flight Check summary (no exact seconds)."""
    if seconds is None:
        return "—"
    if seconds < 60:
        return "under 1m"
    if seconds < 3600:
        return f"{seconds // 60}m"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if minutes:
        return f"{hours}h {minutes}m"
    return f"{hours}h"
