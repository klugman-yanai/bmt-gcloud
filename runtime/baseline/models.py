"""Baseline file and notice models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class BaselineMode(StrEnum):
    BOOTSTRAP = "bootstrap"
    ACTIVE = "active"
    STALE_NOTICE = "stale_notice"


@dataclass(frozen=True, slots=True)
class StableBaselineRecord:
    tag: str
    commit: str
    run_id: str
    promoted_at: str
    aggregate_score: float | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> StableBaselineRecord | None:
        tag = str(payload.get("tag", "")).strip()
        commit = str(payload.get("commit", "")).strip()
        run_id = str(payload.get("run_id", "")).strip()
        promoted_at = str(payload.get("promoted_at", "")).strip()
        if not run_id:
            return None
        score_raw = payload.get("aggregate_score")
        score = float(score_raw) if isinstance(score_raw, (int, float)) else None
        return cls(tag=tag, commit=commit, run_id=run_id, promoted_at=promoted_at, aggregate_score=score)


@dataclass(frozen=True, slots=True)
class BaselineNotice:
    project: str
    leg: str
    mode: BaselineMode
    baseline_tag: str
    baseline_commit: str
    newer_tag: str | None = None
