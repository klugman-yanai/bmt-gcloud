"""PEX commands for stable score baseline promotion."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Annotated, cast

import typer
from whenever import Instant

from cloud_bmt import core, gcs
from cloud_bmt.actions import gh_notice, gh_warning

baseline_app = typer.Typer(help="Score baseline files on the gate bucket.")


def _snapshot_comparison(latest: dict[str, object]) -> str:
    extra = latest.get("extra")
    if isinstance(extra, Mapping):
        scoring_policy = cast(Mapping[str, object], extra).get("scoring_policy")
        if isinstance(scoring_policy, Mapping):
            comparison = cast(Mapping[str, object], scoring_policy).get("comparison")
            if isinstance(comparison, str):
                return comparison.strip().lower()
    verdict_summary = latest.get("verdict_summary")
    if isinstance(verdict_summary, Mapping):
        comparison = cast(Mapping[str, object], verdict_summary).get("comparison")
        if isinstance(comparison, str):
            return comparison.strip().lower()
    return ""


def _validate_promotable_snapshot(*, latest: dict[str, object], slug: str, leg_slug: str, run_id: str) -> None:
    if latest.get("status") != "pass" or latest.get("passed") is not True:
        raise RuntimeError(f"{slug}/{leg_slug} {run_id} is not a passing snapshot")
    reason_code = latest.get("reason_code")
    if reason_code == "all_zero_keyword_hits_warn":
        raise RuntimeError(f"{slug}/{leg_slug} {run_id} is warning-only: all_zero_keyword_hits_warn")
    score = latest.get("aggregate_score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise TypeError(f"{slug}/{leg_slug} {run_id} has no numeric aggregate_score")
    comparison = _snapshot_comparison(latest)
    if comparison == "gte" and float(score) == 0.0:
        raise RuntimeError(f"{slug}/{leg_slug} {run_id} has zero aggregate for a higher-is-better baseline")


@baseline_app.command("promote")
def baseline_promote(
    project: Annotated[str, typer.Argument(help="Gate project slug")],
    leg: Annotated[str, typer.Argument(help="BMT leg slug (e.g. false_rejects)")],
    run_id: Annotated[str, typer.Option("--run-id", help="Snapshot run_id; default last_passing")] = "",
    tag: Annotated[str, typer.Option("--tag", help="Promoted OEM tag label")] = "",
    commit: Annotated[str, typer.Option("--commit", help="Commit SHA")] = "",
) -> None:
    """Write ``stable_baseline.json`` from a green BMT snapshot."""
    bucket = core.require_env("GCS_BUCKET")
    root = core.bucket_root_uri(bucket)
    slug = project.strip().lower()
    leg_slug = leg.strip()
    results_uri = f"{root}/projects/{slug}/results/{leg_slug}"
    current_uri = f"{results_uri}/current.json"
    current, err = gcs.download_json(current_uri)
    if not isinstance(current, dict):
        raise TypeError(f"Missing current.json for {slug}/{leg_slug}: {err}")
    chosen = (run_id or str(current.get("last_passing") or "")).strip()
    if not chosen:
        raise RuntimeError(f"No run_id and no last_passing in {current_uri}")
    latest_uri = f"{results_uri}/snapshots/{chosen}/latest.json"
    latest, lerr = gcs.download_json(latest_uri)
    if not isinstance(latest, dict):
        raise TypeError(f"Missing snapshot latest.json: {lerr}")
    _validate_promotable_snapshot(latest=latest, slug=slug, leg_slug=leg_slug, run_id=chosen)
    score = latest.get("aggregate_score")
    promoted_tag = (tag or os.environ.get("BUILD_REF") or "").strip()
    promoted_commit = (commit or os.environ.get("SOURCE_REF") or os.environ.get("HEAD_SHA") or "").strip()
    payload: dict[str, object] = {
        "tag": promoted_tag,
        "commit": promoted_commit,
        "run_id": chosen,
        "promoted_at": Instant.now().format_iso(unit="second"),
    }
    if isinstance(score, (int, float)):
        payload["aggregate_score"] = float(score)
    dest = f"{results_uri}/stable_baseline.json"
    gcs.upload_json(dest, payload)
    gh_notice(f"Promoted baseline for {slug}/{leg_slug} → {dest} (run_id={chosen})")


@baseline_app.command("preflight-notices")
def baseline_preflight_notices(
    projects: Annotated[str, typer.Option("--projects", help="Comma-separated gate projects")] = "",
) -> None:
    """Emit ::notice:: for missing baselines (never fails the job)."""
    bucket = core.require_env("GCS_BUCKET")
    root = core.bucket_root_uri(bucket)
    from runtime.baseline.resolve import load_stable_baseline_record

    slugs = [p.strip().lower() for p in projects.split(",") if p.strip()]
    if not slugs:
        gh_warning("baseline preflight-notices: no --projects provided")
        return
    for slug in slugs:
        prefix_uri = f"{root}/projects/{slug}/"
        for uri in gcs.list_prefix(prefix_uri):
            rel = uri.removeprefix(prefix_uri)
            if not rel.endswith(".json") or rel.count("/") != 1:
                continue
            leg_name = rel.split("/")[0]
            if leg_name in {"project.json", "plugin-index.json"}:
                continue
            record = load_stable_baseline_record(bucket_root=root, project=slug, leg=leg_name)
            if record is None:
                gh_notice(f"{slug}/{leg_name}: no stable_baseline.json (bootstrap mode for PR BMT)")
