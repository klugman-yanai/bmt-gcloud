from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from runtime.github.check_run_publish import periodic_check_run_progress, resolved_check_run_detail_publish_interval_sec
from runtime.models import ExecutionPlan, StageRuntimePaths

pytestmark = pytest.mark.unit


def test_resolved_interval_defaults_to_milestone_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from runtime.config import constants as c

    monkeypatch.delenv(c.ENV_BMT_CHECK_RUN_DETAIL_PUBLISH_INTERVAL_SEC, raising=False)
    assert resolved_check_run_detail_publish_interval_sec() == 0


def test_resolved_interval_honors_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from runtime.config import constants as c

    monkeypatch.setenv(c.ENV_BMT_CHECK_RUN_DETAIL_PUBLISH_INTERVAL_SEC, "30")
    assert resolved_check_run_detail_publish_interval_sec() == 30


def test_periodic_check_run_progress_publishes_during_leg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from runtime.config import constants as c

    monkeypatch.setenv(c.ENV_BMT_CHECK_RUN_DETAIL_PUBLISH_INTERVAL_SEC, "1")
    calls: list[str] = []

    def _fake_publish(*, plan: ExecutionPlan, runtime: StageRuntimePaths) -> None:
        calls.append(plan.workflow_run_id)

    monkeypatch.setattr("runtime.github_reporting.publish_progress", _fake_publish)
    plan = ExecutionPlan.model_validate(
        {
            "workflow_run_id": "run-1",
            "repository": "org/repo",
            "head_sha": "abc",
            "head_branch": "dev",
            "head_event": "pull_request",
            "pr_number": "1",
            "run_context": "pr",
            "legs": [],
        }
    )
    runtime = StageRuntimePaths(stage_root=tmp_path, workspace_root=tmp_path / "ws")

    with periodic_check_run_progress(plan=plan, runtime=runtime):
        time.sleep(2.2)

    assert calls.count("run-1") >= 2
