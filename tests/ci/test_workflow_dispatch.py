from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

import pytest

from ci.cloud_bmt.workflow_dispatch import (
    WorkflowDispatchInvokePayload,
    WorkflowDispatchManager,
)

pytestmark = pytest.mark.unit


class WorkflowExecutionStubResponse(TypedDict):
    name: str
    state: str


@dataclass
class _WorkflowDispatchSpy:
    """Records arguments passed to the stubbed ``start_execution`` call."""

    project: str | None = None
    region: str | None = None
    workflow_name: str | None = None
    argument: WorkflowDispatchInvokePayload | None = None


def _read_outputs(path: Path) -> dict[str, str]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return dict(line.split("=", 1) for line in lines)


def test_invoke_workflow_starts_execution_and_writes_outputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    github_output = tmp_path / "github_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))
    monkeypatch.setenv("GCP_PROJECT", "demo-project")
    monkeypatch.setenv("CLOUD_RUN_REGION", "europe-west4")
    monkeypatch.setenv("GCS_BUCKET", "demo-bucket")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("HEAD_SHA", "0123456789abcdef0123456789abcdef01234567")
    monkeypatch.setenv("HEAD_BRANCH", "main")
    monkeypatch.setenv("HEAD_EVENT", "push")
    monkeypatch.setenv("RUN_CONTEXT", "ci")
    monkeypatch.setenv("FILTERED_MATRIX_JSON", json.dumps({"include": [{"project": "sk"}, {"project": "sk"}]}))

    spy = _WorkflowDispatchSpy()

    def _fake_start_execution(
        *, project: str, region: str, workflow_name: str, argument: WorkflowDispatchInvokePayload
    ) -> WorkflowExecutionStubResponse:
        spy.project = project
        spy.region = region
        spy.workflow_name = workflow_name
        spy.argument = argument
        return {
            "name": "projects/demo/locations/europe-west4/workflows/bmt-workflow/executions/abc",
            "state": "ACTIVE",
        }

    monkeypatch.setattr("ci.cloud_bmt.workflow_dispatch.start_execution", _fake_start_execution)

    WorkflowDispatchManager.from_env().invoke()

    outputs = _read_outputs(github_output)
    assert outputs["dispatch_confirmed"] == "true"
    assert outputs["workflow_execution_state"] == "ACTIVE"
    assert (
        outputs["workflow_execution_url"] == "https://console.cloud.google.com/workflows/workflow/"
        "europe-west4/bmt-workflow/execution/abc?project=demo-project"
    )
    assert json.loads(outputs["accepted_projects"]) == ["sk"]
    assert spy.project == "demo-project"
    assert spy.region == "europe-west4"
    assert spy.workflow_name == "bmt-workflow"
    assert spy.argument is not None
    assert spy.argument["bucket"] == "demo-bucket"
    assert spy.argument["workflow_run_id"] == "12345"
    assert spy.argument["accepted_projects_json"] == '["sk"]'
    assert spy.argument["force_pass"] is False
    assert spy.argument["active_generation"] == 0


def test_invoke_workflow_force_pass_skips_cloud_dispatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    github_output = tmp_path / "github_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))
    monkeypatch.setenv("GCP_PROJECT", "demo-project")
    monkeypatch.setenv("CLOUD_RUN_REGION", "europe-west4")
    monkeypatch.setenv("GCS_BUCKET", "demo-bucket")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("HEAD_SHA", "0123456789abcdef0123456789abcdef01234567")
    monkeypatch.setenv("HEAD_BRANCH", "main")
    monkeypatch.setenv("HEAD_EVENT", "push")
    monkeypatch.setenv("RUN_CONTEXT", "ci")
    monkeypatch.setenv("FILTERED_MATRIX_JSON", json.dumps({"include": [{"project": "sk"}]}))

    def _boom(
        *, project: str, region: str, workflow_name: str, argument: WorkflowDispatchInvokePayload
    ) -> WorkflowExecutionStubResponse:
        raise RuntimeError("workflows api unavailable")

    monkeypatch.setattr("ci.cloud_bmt.workflow_dispatch.start_execution", _boom)

    WorkflowDispatchManager.from_env().invoke(force_pass=True)
    outputs = _read_outputs(github_output)
    assert outputs["dispatch_confirmed"] == "false"
    assert outputs["dispatch_reason"] == "ok_force_pass_cloud_skipped"


def test_invoke_workflow_pr_lifecycle_supersedes_prior(
    tmp_path: Path,
    monkeypatch,
) -> None:
    github_output = tmp_path / "github_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))
    monkeypatch.setenv("GCP_PROJECT", "demo-project")
    monkeypatch.setenv("CLOUD_RUN_REGION", "europe-west4")
    monkeypatch.setenv("GCS_BUCKET", "demo-bucket")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("HEAD_SHA", "0123456789abcdef0123456789abcdef01234567")
    monkeypatch.setenv("HEAD_BRANCH", "main")
    monkeypatch.setenv("HEAD_EVENT", "pull_request")
    monkeypatch.setenv("PR_NUMBER", "100")
    monkeypatch.setenv("RUN_CONTEXT", "ci")
    monkeypatch.setenv("FILTERED_MATRIX_JSON", json.dumps({"include": [{"project": "sk"}]}))

    cancel_calls: list[str] = []

    def _fake_cancel(*, execution_name: str) -> object:
        cancel_calls.append(execution_name)
        from cloud_bmt.workflows_api import CancelResult

        return CancelResult.BENIGN_TERMINAL

    prior = {
        "pr_number": "100",
        "active_generation": 1,
        "active_commit": "old",
        "github_workflow_run_id": "9999",
        "gcp_execution_name": "projects/demo/locations/europe-west4/workflows/bmt-workflow/executions/old",
        "github_check_run_id": None,
        "status": "running",
        "updated_at": "2026-01-01T00:00:00Z",
    }

    def _fake_read(**kwargs: object) -> tuple[object, int | None]:
        from cloud_bmt.pr_run_registry import PrActiveRecord

        return PrActiveRecord.from_dict(prior), 1

    claim_calls: list[int] = []

    def _fake_claim(**kwargs: object) -> object:
        from cloud_bmt.pr_run_registry import ClaimResult, PrActiveRecord

        claim_calls.append(1)
        record = PrActiveRecord.from_dict(
            {
                **prior,
                "active_generation": 2,
                "github_workflow_run_id": "12345",
                "gcp_execution_name": "projects/demo/locations/europe-west4/workflows/bmt-workflow/executions/abc",
            }
        )
        return ClaimResult(record=record, prior=None, gcs_generation=2)

    monkeypatch.setattr("ci.cloud_bmt.workflow_dispatch.cancel_execution", _fake_cancel)
    monkeypatch.setattr("ci.cloud_bmt.workflow_dispatch.read_record", _fake_read)
    monkeypatch.setattr("ci.cloud_bmt.workflow_dispatch.claim_active_run", _fake_claim)
    monkeypatch.setattr(
        "ci.cloud_bmt.workflow_dispatch.start_execution",
        lambda **kwargs: {
            "name": "projects/demo/locations/europe-west4/workflows/bmt-workflow/executions/abc",
            "state": "ACTIVE",
        },
    )

    WorkflowDispatchManager.from_env().invoke()
    assert cancel_calls == [prior["gcp_execution_name"]]
    assert claim_calls == [1]
    outputs = _read_outputs(github_output)
    assert outputs["dispatch_confirmed"] == "true"
