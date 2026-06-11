from __future__ import annotations

import pytest

from runtime.github.duration_format import (
    floor_duration_for_check_summary,
    format_duration_seconds,
    format_duration_seconds_coarse,
)

pytestmark = pytest.mark.unit


def test_format_duration_seconds_keeps_subminute_precision() -> None:
    assert format_duration_seconds(45) == "45s"
    assert format_duration_seconds(125) == "2m 5s"


def test_format_duration_seconds_coarse_omits_seconds() -> None:
    assert format_duration_seconds_coarse(None) == "—"
    assert format_duration_seconds_coarse(0) == "under 1m"
    assert format_duration_seconds_coarse(45) == "under 1m"
    assert format_duration_seconds_coarse(125) == "2m"
    assert format_duration_seconds_coarse(3661) == "1h 1m"


def test_floor_duration_for_check_summary_respects_bucket() -> None:
    assert floor_duration_for_check_summary(125, bucket_sec=60) == 120
    assert floor_duration_for_check_summary(125, bucket_sec=0) == 120
    assert floor_duration_for_check_summary(45, bucket_sec=60) == 0
    assert floor_duration_for_check_summary(45, bucket_sec=0) == 0
