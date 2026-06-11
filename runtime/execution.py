"""Execute a planned leg using the new plugin contract."""

from __future__ import annotations

import json
import os
from pathlib import Path

from bmt_sdk.context import ExecutionContext
from bmt_sdk.models import (
    BmtManifestView,
    ExecutionConfigView,
    ProjectManifestView,
    RunnerConfigView,
)
from bmt_sdk.results import ExecutionResult, PreparedAssets, ScoreResult, VerdictResult

from runtime.baseline.resolve import resolve_leg_baseline_context
from runtime.config.constants import ENV_GCS_BUCKET
from runtime.models import (
    BmtManifest,
    ExecutionPlan,
    LegSummary,
    PlanLeg,
    ProjectManifest,
    ScorePayload,
    StageRuntimePaths,
)
from runtime.plugin_contract import resolve_plugin_id, resolve_plugin_version
from runtime.plugin_host.direct_client import execute_plugin_direct

_MAX_RUN_NOTES = 20
_MAX_RUN_NOTE_CHARS = 1000


def _run_notes_from_plugin_config(plugin_config: dict[str, object]) -> list[str]:
    raw = plugin_config.get("run_notes")
    if isinstance(raw, str):
        candidates: list[object] = [raw]
    elif isinstance(raw, (list, tuple)):
        candidates = list(raw)
    else:
        return []

    notes: list[str] = []
    for value in candidates:
        if not isinstance(value, str):
            continue
        note = value.strip()
        if not note:
            continue
        if len(note) > _MAX_RUN_NOTE_CHARS:
            note = note[: _MAX_RUN_NOTE_CHARS - 3].rstrip() + "..."
        notes.append(note)
        if len(notes) >= _MAX_RUN_NOTES:
            break
    return notes


def _make_manifest_view(m: BmtManifest, *, execution_profile: str | None = None) -> BmtManifestView:
    profile = execution_profile if execution_profile is not None else m.execution.profile
    return BmtManifestView(
        project=m.project,
        bmt_slug=m.bmt_slug,
        bmt_id=m.bmt_id,
        enabled=m.enabled,
        plugin_config=dict(m.plugin_config),
        inputs_prefix=m.inputs_prefix,
        results_prefix=str(m.results_path),  # ResultsPath is NewType[str]; non-empty invariant enforced by BmtManifest
        outputs_prefix=m.outputs_prefix,
        execution=ExecutionConfigView(
            policy=m.execution.policy,
            profile=profile,
        ),
        runner=RunnerConfigView(
            uri=m.runner.uri,
            deps_prefix=m.runner.deps_prefix,
            template_path=m.runner.template_path,
        ),
    )


def _assert_runner_pin_for_ci(*, plan: ExecutionPlan, leg: PlanLeg, runtime: StageRuntimePaths) -> None:
    """Fail the leg when gate runner_meta.source_ref does not match the commit under test."""
    head_sha = (plan.head_sha or "").strip()
    if not head_sha or (plan.run_context or "").strip() not in ("", "ci"):
        return
    meta_path = runtime.stage_root / "projects" / leg.project / "runner_meta.json"
    if not meta_path.is_file():
        return
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    if not isinstance(payload, dict):
        return
    source_ref = str(payload.get("source_ref", "")).strip()
    if source_ref and source_ref != head_sha:
        raise RuntimeError(
            f"Runner pin mismatch for {leg.project}: gate runner source_ref={source_ref[:12]} "
            f"!= HEAD_SHA={head_sha[:12]}"
        )


def _make_project_view(p: ProjectManifest) -> ProjectManifestView:
    return ProjectManifestView(
        project=p.project,
        description=p.description,
    )


def _execute_plugin_hooks(
    *,
    project_root: Path,
    context: ExecutionContext,
    bmt_manifest: BmtManifest,
    leg: PlanLeg,
    baseline: ScoreResult | None,
) -> tuple[PreparedAssets, ExecutionResult, ScoreResult, VerdictResult, str]:
    plugin_id = resolve_plugin_id(leg.project, bmt_manifest.plugin_id)

    plugin_py = project_root / "plugin.py"
    if not plugin_py.is_file():
        raise FileNotFoundError(f"Plugin entrypoint requires plugin.py at {plugin_py}")
    prepared, execution, score, verdict = execute_plugin_direct(
        project_dir=project_root,
        context=context,
        baseline=baseline,
    )
    return prepared, execution, score, verdict, plugin_id


def execute_leg(*, plan: ExecutionPlan, leg: PlanLeg, runtime: StageRuntimePaths) -> LegSummary:
    manifest_path = runtime.stage_root / leg.manifest_path
    bmt_manifest = BmtManifest.from_flat_file(manifest_path)
    project_manifest_path = runtime.stage_root / "projects" / leg.project / "project.json"
    project_manifest = ProjectManifest.model_validate(json.loads(project_manifest_path.read_text(encoding="utf-8")))
    project_root = runtime.stage_root / "projects" / leg.project
    plugin_root = project_root

    run_root = runtime.workspace_root / leg.project / leg.bmt_slug / leg.run_id
    outputs_root = run_root / "outputs"
    logs_root = run_root / "logs"
    outputs_root.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)

    deps_prefix = bmt_manifest.runner.deps_prefix.strip()
    case_progress_root = (
        runtime.stage_root / "triggers" / "case-progress" / plan.workflow_run_id / f"{leg.project}-{leg.bmt_slug}"
    )
    context = ExecutionContext(
        project_manifest=_make_project_view(project_manifest),
        bmt_manifest=_make_manifest_view(bmt_manifest, execution_profile=leg.execution_profile),
        plugin_root=plugin_root,
        workspace_root=run_root,
        dataset_root=runtime.stage_root / bmt_manifest.inputs_prefix,
        outputs_root=outputs_root,
        logs_root=logs_root,
        runner_path=(runtime.stage_root / bmt_manifest.runner.uri) if bmt_manifest.runner.uri else None,
        deps_root=(runtime.stage_root / deps_prefix) if deps_prefix else None,
        case_progress_root=case_progress_root,
    )
    _assert_runner_pin_for_ci(plan=plan, leg=leg, runtime=runtime)

    bucket = (os.environ.get(ENV_GCS_BUCKET) or "").strip()
    bucket_root = f"gs://{bucket}" if bucket else ""
    _mode, _record, baseline_notice, score_baseline = resolve_leg_baseline_context(
        bucket_root=bucket_root,
        project=leg.project,
        leg=leg.bmt_slug,
        stage_root=runtime.stage_root,
        core_main_repository=os.environ.get("CORE_MAIN_REPOSITORY") or "Cloud Bench-org/core-main",
    )

    _prepared, execution_result, score, verdict, plugin_id = _execute_plugin_hooks(
        project_root=project_root,
        context=context,
        bmt_manifest=bmt_manifest,
        leg=leg,
        baseline=score_baseline,
    )
    score_extra = dict(score.extra)
    run_notes = _run_notes_from_plugin_config(bmt_manifest.plugin_config)
    if run_notes:
        score_extra["run_notes"] = run_notes
    if baseline_notice is not None:
        score_extra["baseline_mode"] = baseline_notice.mode.value
        if baseline_notice.baseline_tag:
            score_extra["baseline_tag"] = baseline_notice.baseline_tag
        if baseline_notice.newer_tag:
            score_extra["baseline_newer_tag"] = baseline_notice.newer_tag

    plugin_version = resolve_plugin_version(bmt_manifest.plugin_version)

    return LegSummary(
        project=leg.project,
        bmt_slug=leg.bmt_slug,
        bmt_id=leg.bmt_id,
        run_id=leg.run_id,
        status=verdict.status,
        reason_code=verdict.reason_code,
        plugin_id=plugin_id,
        plugin_version=plugin_version,
        execution_mode_used=execution_result.execution_mode_used,
        score=ScorePayload(
            aggregate_score=score.aggregate_score,
            metrics=score.metrics,
            extra=score_extra,
        ),
        verdict_summary=verdict.summary,
    )
