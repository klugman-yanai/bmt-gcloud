from __future__ import annotations

from pathlib import Path

import pytest

from runtime.artifacts import load_optional_reporting_metadata, write_reporting_metadata
from runtime.config.bmt_domain_status import BmtLegStatus
from runtime.github_reporting import publish_final_results
from runtime.models import ExecutionPlan, LegSummary, ReportingMetadata, ScorePayload, StageRuntimePaths


def _leg_pass() -> LegSummary:
    return LegSummary(
        project="sk",
        bmt_slug="demo",
        bmt_id="demo",
        run_id="run-1",
        status=BmtLegStatus.PASS.value,
        reason_code="ok",
        plugin_ref="direct",
        execution_mode_used="cloud",
        score=ScorePayload(aggregate_score=1.0, extra={}),
    )


def test_publish_final_results_retries_post_final_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("runtime.github_reporting.time.sleep", lambda *_a, **_k: None)
    stage_root = tmp_path / "stage"
    stage_root.mkdir(parents=True, exist_ok=True)
    plan = ExecutionPlan(
        workflow_run_id="wf-retry-status",
        repository="o/r",
        head_sha="a" * 40,
        head_branch="main",
        head_event="push",
        pr_number="",
        legs=[],
        standard_task_count=0,
        heavy_task_count=0,
    )
    write_reporting_metadata(
        stage_root=stage_root,
        workflow_run_id=plan.workflow_run_id,
        metadata=ReportingMetadata(
            workflow_execution_url="https://wf.example/x",
            check_run_id=1,
            started_at="2026-05-11T00:00:00Z",
        ),
    )
    runtime = StageRuntimePaths(stage_root=stage_root, workspace_root=tmp_path / "ws")

    calls: list[int] = []

    class _Reporter:
        repository = plan.repository
        sha = plan.head_sha
        token = "t"
        status_context = plan.status_context

        def finalize_check_run(self, **_k: object) -> tuple[object, bool]:
            return None, True

        def post_final_status(self, **_k: object) -> bool:
            calls.append(len(calls))
            return len(calls) >= 3

    def _fake_load_reporter(**_k: object) -> tuple[object, ReportingMetadata]:
        meta = load_optional_reporting_metadata(
            stage_root=stage_root, workflow_run_id=plan.workflow_run_id
        )
        assert meta is not None
        return _Reporter(), meta

    monkeypatch.setattr("runtime.github_reporting._load_reporter", _fake_load_reporter)
    monkeypatch.setattr("runtime.github_reporting._write_log_dump_and_sign", lambda **_k: None)
    monkeypatch.setattr("runtime.github_reporting.resolve_github_app_token", lambda _repo: "tok")

    publish_final_results(plan=plan, summaries=[_leg_pass()], runtime=runtime)
    assert len(calls) == 3
