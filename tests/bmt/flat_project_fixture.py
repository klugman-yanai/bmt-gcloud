"""Shared flat-layout project tree for integration tests."""

from __future__ import annotations

import json
import uuid
from pathlib import Path


def write_flat_project(
    stage_root: Path,
    project: str,
    bmt_slug: str,
    *,
    plugin_config: dict | None = None,
    plugin_runtime: str = "",
    python_dependencies: list[str] | None = None,
) -> None:
    """Set up a flat-layout project with direct ``plugin.py`` execution."""
    project_dir = stage_root / "projects" / project
    project_dir.mkdir(parents=True, exist_ok=True)
    project_payload: dict[str, object] = {"schema_version": 1, "project": project}
    if plugin_runtime:
        project_payload["plugin_runtime"] = plugin_runtime
    if python_dependencies is not None:
        project_payload["python_dependencies"] = python_dependencies
    (project_dir / "project.json").write_text(
        json.dumps(project_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    bmt_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://bmt/{project}/{bmt_slug}"))
    (project_dir / f"{bmt_slug}.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project": project,
                "bmt_slug": bmt_slug,
                "bmt_id": bmt_id,
                "enabled": True,
                "inputs_prefix": f"projects/{project}/inputs/{bmt_slug}",
                "results_prefix": f"projects/{project}/results/{bmt_slug}",
                "outputs_prefix": f"projects/{project}/outputs/{bmt_slug}",
                "runner": {"uri": "", "deps_prefix": "", "template_path": "runtime/assets/cloud_bench_input_template.json"},
                "execution": {"policy": "adaptive_batch_then_legacy"},
                "plugin_config": plugin_config or {"pass_threshold": 1.0},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_dir / "plugin.py").write_text(
        """from __future__ import annotations

from bmt_sdk import averaged_result, custom_plugin
from bmt_sdk.context import ExecutionContext
from bmt_sdk.results import (
    CaseResult,
    ExecutionResult,
    PreparedAssets,
    ScoreResult,
    VerdictResult,
    pass_verdict,
)
from runtime.config.bmt_domain_status import BmtLegStatus


def prepare(context: ExecutionContext) -> PreparedAssets:
    return context.prepared_assets()


def execute(context: ExecutionContext, prepared_assets: PreparedAssets) -> ExecutionResult:
    del prepared_assets
    case_results: list[CaseResult] = []
    for wav_path in sorted(context.dataset_root.rglob("*.wav")):
        rel = wav_path.relative_to(context.dataset_root).as_posix()
        case_results.append(
            CaseResult(case_id=rel, input_path=wav_path, exit_code=0, status="ok", metrics={"score": 1.0})
        )
    return ExecutionResult(execution_mode_used="plugin_direct", case_results=case_results)


def score(
    execution_result: ExecutionResult,
    baseline: ScoreResult | None,
    context: ExecutionContext,
) -> ScoreResult:
    del baseline, context
    aggregate = 1.0 if execution_result.case_results else 0.0
    return ScoreResult(
        aggregate_score=aggregate,
        metrics={"case_count": len(execution_result.case_results)},
        extra={},
    )


def evaluate(
    score_result: ScoreResult,
    baseline: ScoreResult | None,
    context: ExecutionContext,
) -> VerdictResult:
    del baseline, context
    passed = score_result.aggregate_score >= 1.0
    if passed:
        return pass_verdict(
            reason_code="score_above_threshold",
            summary={"aggregate_score": score_result.aggregate_score},
        )
    return VerdictResult(
        passed=False,
        status=BmtLegStatus.FAIL.value,
        reason_code="score_below_threshold",
        summary={"aggregate_score": score_result.aggregate_score},
    )


def plugin():
    return custom_plugin(
        project="demo",
        scoring=averaged_result("score"),
        prepare=prepare,
        execute=execute,
        score=score,
        evaluate=evaluate,
    )
""",
        encoding="utf-8",
    )
