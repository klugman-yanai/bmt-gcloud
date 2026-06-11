from __future__ import annotations

import json
from pathlib import Path

import pytest
from _pytest.monkeypatch import MonkeyPatch

import runtime.entrypoint as runtime_entrypoint
import runtime.main as image_main
from runtime.artifacts import load_summary, write_reporting_metadata
from runtime.entrypoint import run_coordinator_mode, run_plan_mode, run_task_mode
from runtime.models import ReportingMetadata
from tests.bmt.flat_project_fixture import write_flat_project

pytestmark = pytest.mark.integration


def test_runtime_modes_write_plan_summary_and_pointer(tmp_path: Path, monkeypatch) -> None:
    stage_root = tmp_path / "gcp" / "stage"
    workspace_root = tmp_path / "workspace"
    write_flat_project(stage_root, "acme", "wake_word_quality")

    dataset_root = stage_root / "projects" / "acme" / "inputs" / "wake_word_quality"
    dataset_root.mkdir(parents=True, exist_ok=True)
    (dataset_root / "sample.wav").write_bytes(b"fake")

    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("BMT_HEAD_SHA", "0123456789abcdef0123456789abcdef01234567")
    monkeypatch.setenv("BMT_HEAD_BRANCH", "main")
    monkeypatch.setenv("BMT_ACCEPTED_PROJECTS_JSON", '["acme"]')

    assert run_plan_mode(workflow_run_id="wf-123", stage_root=stage_root) == 0
    assert (
        run_task_mode(
            workflow_run_id="wf-123",
            task_profile="standard",
            task_index=0,
            stage_root=stage_root,
            workspace_root=workspace_root,
        )
        == 0
    )
    # Coordinator skips ephemeral cleanup unless GitHub publish completed; local
    # integration has no GitHub — mark publish complete so triggers/ is pruned.
    write_reporting_metadata(
        stage_root=stage_root,
        workflow_run_id="wf-123",
        metadata=ReportingMetadata(
            workflow_execution_url="https://example.test/workflows/wf-123",
            check_run_id=1,
            started_at="2026-01-01T00:00:00Z",
            github_publish_complete=True,
        ),
    )
    assert run_coordinator_mode(workflow_run_id="wf-123", stage_root=stage_root) == 0

    plan_path = stage_root / "triggers" / "plans" / "wf-123.json"
    summary_path = stage_root / "triggers" / "summaries" / "wf-123" / "acme-wake_word_quality.json"
    pointer_path = stage_root / "projects" / "acme" / "results" / "wake_word_quality" / "current.json"
    assert not plan_path.is_file()
    assert not summary_path.is_file()
    assert pointer_path.is_file()

    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert pointer["latest"] == "wf-123-wake_word_quality"
    assert pointer["last_passing"] == "wf-123-wake_word_quality"


def test_run_task_mode_writes_failure_summary_when_execute_leg_raises(tmp_path: Path, monkeypatch) -> None:
    stage_root = tmp_path / "gcp" / "stage"
    workspace_root = tmp_path / "workspace"
    write_flat_project(stage_root, "acme", "wake_word_quality")

    dataset_root = stage_root / "projects" / "acme" / "inputs" / "wake_word_quality"
    dataset_root.mkdir(parents=True, exist_ok=True)
    (dataset_root / "sample.wav").write_bytes(b"fake")

    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("BMT_HEAD_SHA", "0123456789abcdef0123456789abcdef01234567")
    monkeypatch.setenv("BMT_HEAD_BRANCH", "main")
    monkeypatch.setenv("BMT_ACCEPTED_PROJECTS_JSON", '["acme"]')

    def boom(**_kwargs: object) -> None:
        raise RuntimeError("injected execute_leg failure")

    monkeypatch.setattr(runtime_entrypoint, "execute_leg", boom)

    assert run_plan_mode(workflow_run_id="wf-err", stage_root=stage_root) == 0
    assert (
        run_task_mode(
            workflow_run_id="wf-err",
            task_profile="standard",
            task_index=0,
            stage_root=stage_root,
            workspace_root=workspace_root,
        )
        == 0
    )
    summary = load_summary(
        stage_root=stage_root,
        workflow_run_id="wf-err",
        project="acme",
        bmt_slug="wake_word_quality",
    )
    assert summary.status == "fail"
    assert summary.reason_code == "runner_failures"
    assert summary.score.extra.get("unavailable") is True


def test_image_main_dispatches_task_mode(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    def fake_run_task_mode(
        *,
        workflow_run_id: str,
        task_profile: str,
        task_index: int,
        stage_root: Path | None = None,
        workspace_root: Path | None = None,
    ) -> int:
        called.update(
            {
                "workflow_run_id": workflow_run_id,
                "task_profile": task_profile,
                "task_index": task_index,
                "stage_root": stage_root,
                "workspace_root": workspace_root,
            }
        )
        return 0

    monkeypatch.setattr(runtime_entrypoint, "run_task_mode", fake_run_task_mode)
    monkeypatch.setenv("BMT_MODE", "task")
    monkeypatch.setenv("BMT_WORKFLOW_RUN_ID", "wf-456")
    monkeypatch.setenv("BMT_TASK_PROFILE", "heavy")
    monkeypatch.setenv("CLOUD_RUN_TASK_INDEX", "2")
    monkeypatch.setenv("BMT_RUNTIME_ROOT", str(tmp_path / "stage"))
    monkeypatch.setenv("BMT_FRAMEWORK_WORKSPACE", str(tmp_path / "workspace"))

    assert image_main.main() == 0
    assert called == {
        "workflow_run_id": "wf-456",
        "task_profile": "heavy",
        "task_index": 2,
        "stage_root": (tmp_path / "stage").resolve(),
        "workspace_root": (tmp_path / "workspace").resolve(),
    }
