from __future__ import annotations

from pathlib import Path

import pytest

from runtime.execution import execute_leg
from runtime.models import StageRuntimePaths, WorkflowRequest
from runtime.planning import PlanOptions, build_plan
from tests.bmt.flat_project_fixture import write_flat_project

pytestmark = pytest.mark.integration


def _execute_for_project(
    tmp_path: Path,
    *,
    plugin_runtime: str = "",
    python_dependencies: list[str] | None = None,
) -> str:
    stage_root = tmp_path / "gcp" / "stage"
    workspace_root = tmp_path / "workspace"
    write_flat_project(
        stage_root,
        "acme",
        "wake_word_quality",
        plugin_runtime=plugin_runtime,
        python_dependencies=python_dependencies,
    )
    dataset_root = stage_root / "projects" / "acme" / "inputs" / "wake_word_quality"
    dataset_root.mkdir(parents=True, exist_ok=True)
    (dataset_root / "sample.wav").write_bytes(b"fake")
    plan = build_plan(
        runtime=StageRuntimePaths(stage_root=stage_root, workspace_root=workspace_root),
        options=PlanOptions(request=WorkflowRequest(workflow_run_id="wf-rt", accepted_projects=["acme"])),
    )
    summary = execute_leg(
        plan=plan,
        leg=plan.legs[0],
        runtime=StageRuntimePaths(stage_root=stage_root, workspace_root=workspace_root),
    )
    return summary.execution_mode_used


def test_plugin_py_is_entrypoint_even_when_runtime_is_worker(tmp_path: Path) -> None:
    assert _execute_for_project(tmp_path, plugin_runtime="worker") == "plugin_direct"


def test_plugin_py_is_entrypoint_when_dependencies_declared(tmp_path: Path) -> None:
    assert _execute_for_project(tmp_path, python_dependencies=["requests>=2"]) == "plugin_direct"
