"""Cross-cutting tests for BMT Gate terminal reporting (orphan prevention)."""

from __future__ import annotations

from pathlib import Path

import pytest

from runtime.artifacts import (
    cleanup_ephemeral_triggers,
    load_optional_reporting_metadata,
    write_plan,
    write_reporting_metadata,
)
from runtime.config.bmt_domain_status import BmtLegStatus
from runtime.entrypoint import run_coordinator_mode, run_finalize_failure_mode
from runtime.github_reporting import close_check_from_stage, publish_github_failure
from runtime.models import ExecutionPlan, LegSummary, ReportingMetadata, ScorePayload, StageRuntimePaths

pytestmark = pytest.mark.unit


def _plan(*, workflow_run_id: str = "wf-terminal", check_run_id: int | None = 42) -> ExecutionPlan:
    return ExecutionPlan(
        workflow_run_id=workflow_run_id,
        repository="owner/repo",
        head_sha="0" * 40,
        head_branch="main",
        head_event="push",
        pr_number="",
        legs=[],
        standard_task_count=0,
        heavy_task_count=0,
        github_check_run_id=check_run_id,
    )


def test_cleanup_skipped_when_github_publish_incomplete(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    plan = _plan()
    write_plan(stage_root=stage, plan=plan)
    write_reporting_metadata(
        stage_root=stage,
        workflow_run_id=plan.workflow_run_id,
        metadata=ReportingMetadata(
            workflow_execution_url="https://example.test/wf",
            check_run_id=42,
            started_at="2026-03-19T10:00:00Z",
            github_publish_complete=False,
        ),
    )
    (stage / "triggers" / "plans").mkdir(parents=True, exist_ok=True)

    cleanup_ephemeral_triggers(stage_root=stage, plan=plan, github_publish_complete=False)

    assert (stage / "triggers" / "plans" / f"{plan.workflow_run_id}.json").is_file()
    assert load_optional_reporting_metadata(stage_root=stage, workflow_run_id=plan.workflow_run_id) is not None


def test_publish_github_failure_uses_plan_check_run_id_without_reporting_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path / "stage"
    plan = _plan(check_run_id=77)
    write_plan(stage_root=stage, plan=plan)
    runtime = StageRuntimePaths(stage_root=stage, workspace_root=stage / "ws")
    closed: list[bool] = []

    def _fake_close(**_kwargs: object) -> bool:
        closed.append(True)
        write_reporting_metadata(
            stage_root=stage,
            workflow_run_id=plan.workflow_run_id,
            metadata=ReportingMetadata(
                workflow_execution_url="https://example.test/wf",
                check_run_id=77,
                started_at="2026-03-19T10:00:00Z",
                github_publish_complete=True,
            ),
        )
        return True

    monkeypatch.setenv("BMT_WORKFLOW_EXECUTION_URL", "https://example.test/wf")
    monkeypatch.setattr("runtime.github_reporting.resolve_github_app_token", lambda _repo: "token")
    monkeypatch.setattr("runtime.github_reporting.publish_final_results", lambda **_k: None)
    monkeypatch.setattr("runtime.github_reporting.close_check_from_stage", _fake_close)

    publish_github_failure(plan=plan, runtime=runtime, reason="workflow aborted")

    assert closed == [True]


def test_close_check_from_stage_sets_failure_banner_when_legs_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path / "stage"
    plan = _plan()
    runtime = StageRuntimePaths(stage_root=stage, workspace_root=stage / "ws")
    summaries = [
        LegSummary(
            project="sk",
            bmt_slug="false_rejects",
            bmt_id="id",
            run_id="r1",
            status=BmtLegStatus.PASS.value,
            reason_code="ok",
            execution_mode_used="standard",
            score=ScorePayload(aggregate_score=1.0),
            verdict_summary={},
        )
    ]
    captured: dict[str, object] = {}

    class _Reporter:
        def finalize_check_run(self, *, check_run_id: int | None, view: object, details_url: str) -> tuple[int, bool]:
            captured["banner"] = getattr(view, "publish_failure_banner", "")
            captured["state"] = getattr(view, "state", "")
            return check_run_id or 0, True

        def post_final_status(self, *, state: str, description: str, details_url: str | None) -> bool:
            captured["commit_state"] = state
            return True

    monkeypatch.setattr(
        "runtime.github_reporting.GitHubReporter",
        lambda **_k: _Reporter(),
    )
    monkeypatch.setattr("runtime.github_reporting._write_log_dump_and_sign", lambda **_k: None)

    ok = close_check_from_stage(
        plan=plan,
        runtime=runtime,
        summaries=summaries,
        reason="GitHub API unavailable",
        metadata=ReportingMetadata(workflow_execution_url="https://example.test/wf", check_run_id=42),
        token="tok",  # noqa: S106
        force_failure_conclusion=True,
    )

    assert ok is True
    assert "Results passed in GCS" in str(captured.get("banner", ""))
    assert captured.get("state") == "failure"


def test_coordinator_skips_cleanup_when_publish_stays_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path / "stage"
    plan = _plan()
    write_plan(stage_root=stage, plan=plan)
    write_reporting_metadata(
        stage_root=stage,
        workflow_run_id=plan.workflow_run_id,
        metadata=ReportingMetadata(
            workflow_execution_url="https://example.test/wf",
            check_run_id=9,
            started_at="2026-03-19T10:00:00Z",
            github_publish_complete=False,
        ),
    )
    cleanup_flags: list[bool] = []

    def _track_cleanup(*, github_publish_complete: bool, **_kwargs: object) -> None:
        cleanup_flags.append(github_publish_complete)

    monkeypatch.setattr("runtime.entrypoint.publish_final_results", lambda **_k: None)
    monkeypatch.setattr("runtime.entrypoint.publish_github_failure", lambda **_k: None)
    monkeypatch.setattr("runtime.entrypoint.cleanup_ephemeral_triggers", _track_cleanup)

    assert run_coordinator_mode(workflow_run_id=plan.workflow_run_id, stage_root=stage) == 0
    assert cleanup_flags == []


def test_finalize_failure_closes_check_using_plan_mirror_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stage = tmp_path / "stage"
    plan = _plan(check_run_id=3)
    write_plan(stage_root=stage, plan=plan)
    captured: list[str] = []

    def _capture_failure(*, reason: str, **_kwargs: object) -> None:
        captured.append(reason)

    monkeypatch.setattr("runtime.entrypoint.publish_github_failure", _capture_failure)

    assert run_finalize_failure_mode(workflow_run_id=plan.workflow_run_id, stage_root=stage) == 0
    assert captured and "BMT Google Workflow aborted" in captured[0]
