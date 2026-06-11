from __future__ import annotations

from pathlib import Path

import pytest

from runtime.execution import execute_leg
from runtime.models import StageRuntimePaths, WorkflowRequest
from runtime.planning import PlanOptions, build_plan
from tests.bmt.flat_project_fixture import write_flat_project

pytestmark = pytest.mark.integration


def test_planner_discovers_enabled_bmt_and_executor_runs_plugin(tmp_path: Path) -> None:
    """Flat-layout: planner discovers enabled BMT and executor loads plugin directly."""
    stage_root = tmp_path / "gcp" / "stage"
    workspace_root = tmp_path / "workspace"
    write_flat_project(stage_root, "acme", "wake_word_quality")

    dataset_root = stage_root / "projects" / "acme" / "inputs" / "wake_word_quality"
    dataset_root.mkdir(parents=True, exist_ok=True)
    (dataset_root / "sample.wav").write_bytes(b"fake")

    plan = build_plan(
        runtime=StageRuntimePaths(stage_root=stage_root, workspace_root=workspace_root),
        options=PlanOptions(
            request=WorkflowRequest(workflow_run_id="wf-123", accepted_projects=["acme"]),
        ),
    )

    assert len(plan.legs) == 1
    assert plan.legs[0].plugin_id == "acme.default"
    summary = execute_leg(
        plan=plan,
        leg=plan.legs[0],
        runtime=StageRuntimePaths(stage_root=stage_root, workspace_root=workspace_root),
    )
    assert summary.execution_mode_used == "plugin_direct"


def test_executor_copies_manifest_run_notes_to_score_extra(tmp_path: Path) -> None:
    stage_root = tmp_path / "gcp" / "stage"
    workspace_root = tmp_path / "workspace"
    write_flat_project(
        stage_root,
        "acme",
        "wake_word_quality",
        plugin_config={
            "pass_threshold": 1.0,
            "run_notes": ["Use the current runner/lib builds; this run intentionally exposes loader regressions."],
        },
    )

    dataset_root = stage_root / "projects" / "acme" / "inputs" / "wake_word_quality"
    dataset_root.mkdir(parents=True, exist_ok=True)
    (dataset_root / "sample.wav").write_bytes(b"fake")

    plan = build_plan(
        runtime=StageRuntimePaths(stage_root=stage_root, workspace_root=workspace_root),
        options=PlanOptions(
            request=WorkflowRequest(workflow_run_id="wf-123", accepted_projects=["acme"]),
        ),
    )

    summary = execute_leg(
        plan=plan,
        leg=plan.legs[0],
        runtime=StageRuntimePaths(stage_root=stage_root, workspace_root=workspace_root),
    )
    assert summary.score.extra.get("run_notes") == [
        "Use the current runner/lib builds; this run intentionally exposes loader regressions."
    ]
