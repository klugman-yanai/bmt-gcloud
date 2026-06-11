"""Load stable baselines and resolve per-leg modes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from bmt_sdk.results import ScoreResult

from runtime.baseline.gcs_json import download_json
from runtime.baseline.github_tags import newest_mapped_tag_for_project
from runtime.baseline.models import BaselineMode, BaselineNotice, StableBaselineRecord
from runtime.baseline.tags import parse_release_tag, tag_version_key


def _stable_baseline_uri(bucket_root: str, project: str, leg: str) -> str:
    return f"{bucket_root.rstrip('/')}/projects/{project}/results/{leg}/stable_baseline.json"


def _snapshot_latest_uri(bucket_root: str, project: str, leg: str, run_id: str) -> str:
    return f"{bucket_root.rstrip('/')}/projects/{project}/results/{leg}/snapshots/{run_id}/latest.json"


def load_stable_baseline_record(*, bucket_root: str, project: str, leg: str) -> StableBaselineRecord | None:
    payload, _err = download_json(_stable_baseline_uri(bucket_root, project, leg))
    if not isinstance(payload, dict):
        return None
    return StableBaselineRecord.from_payload(payload)


def load_stable_baseline_record_local(stage_root: Path, project: str, leg: str) -> StableBaselineRecord | None:
    path = stage_root / "projects" / project / "results" / leg / "stable_baseline.json"
    if not path.is_file():
        return None
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return StableBaselineRecord.from_payload(payload)


def load_score_baseline_from_gcs(
    *,
    bucket_root: str,
    project: str,
    leg: str,
    stage_root: Path | None = None,
) -> ScoreResult | None:
    record = load_stable_baseline_record(bucket_root=bucket_root, project=project, leg=leg)
    if record is None and stage_root is not None:
        record = load_stable_baseline_record_local(stage_root, project, leg)
    if record is None:
        return None
    latest, _err = download_json(_snapshot_latest_uri(bucket_root, project, leg, record.run_id))
    if not isinstance(latest, dict):
        return None
    score = latest.get("aggregate_score")
    if not isinstance(score, (int, float)):
        return None
    metrics_raw = latest.get("metrics")
    metrics: dict[str, Any] = cast(dict[str, Any], metrics_raw) if isinstance(metrics_raw, dict) else {}
    return ScoreResult(aggregate_score=float(score), metrics=metrics, extra={"baseline_run_id": record.run_id})


def _tag_is_newer(promoted_tag: str, newer: str) -> bool:
    p = parse_release_tag(promoted_tag)
    n = parse_release_tag(newer)
    if p is None or n is None or p[0] != n[0]:
        return False
    pv = tag_version_key(p[1])
    nv = tag_version_key(n[1])
    if pv is None or nv is None:
        return newer.strip().lower() != promoted_tag.strip().lower()
    return nv > pv


def resolve_baseline_mode(
    *,
    record: StableBaselineRecord | None,
    gate_project: str,
    core_main_repository: str | None = None,
) -> BaselineMode:
    if record is None:
        return BaselineMode.BOOTSTRAP
    newer = newest_mapped_tag_for_project(gate_project, repository=core_main_repository)
    if newer and record.tag and _tag_is_newer(record.tag, newer):
        return BaselineMode.STALE_NOTICE
    return BaselineMode.ACTIVE


def resolve_leg_baseline_context(
    *,
    bucket_root: str,
    project: str,
    leg: str,
    stage_root: Path | None = None,
    core_main_repository: str | None = None,
) -> tuple[BaselineMode, StableBaselineRecord | None, BaselineNotice | None, ScoreResult | None]:
    record = load_stable_baseline_record(bucket_root=bucket_root, project=project, leg=leg)
    if record is None and stage_root is not None:
        record = load_stable_baseline_record_local(stage_root, project, leg)
    mode = resolve_baseline_mode(
        record=record,
        gate_project=project,
        core_main_repository=core_main_repository,
    )
    score = load_score_baseline_from_gcs(
        bucket_root=bucket_root,
        project=project,
        leg=leg,
        stage_root=stage_root,
    )
    notice: BaselineNotice | None = None
    if mode == BaselineMode.BOOTSTRAP:
        notice = BaselineNotice(project=project, leg=leg, mode=mode, baseline_tag="", baseline_commit="")
    elif record is not None:
        newer = (
            newest_mapped_tag_for_project(project, repository=core_main_repository)
            if mode == BaselineMode.STALE_NOTICE
            else None
        )
        notice = BaselineNotice(
            project=project,
            leg=leg,
            mode=mode,
            baseline_tag=record.tag,
            baseline_commit=record.commit[:7] if record.commit else "",
            newer_tag=newer,
        )
    return mode, record, notice, score


def format_baseline_notice_line(notice: BaselineNotice) -> str:
    if notice.mode == BaselineMode.BOOTSTRAP:
        return f"- **{notice.project}/{notice.leg}:** Baseline: none (bootstrap — first run for this leg)"
    line = f"- **{notice.project}/{notice.leg}:** Baseline: {notice.baseline_tag}"
    if notice.baseline_commit:
        line += f" @ {notice.baseline_commit}"
    if notice.mode == BaselineMode.STALE_NOTICE and notice.newer_tag:
        line += f" — note: newer tag `{notice.newer_tag}` exists; baseline not updated yet"
    return line
