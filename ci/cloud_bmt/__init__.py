"""Cloud Bench CI driver: matrix, trigger, Cloud Run handoff, runner upload."""

from __future__ import annotations

__all__ = [
    "get_config",
    "get_context",
]

from cloud_bmt import config

get_config = config.get_config
get_context = config.get_context
