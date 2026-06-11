"""Direct GitHub -> Workflows handoff for the Cloud Run BMT pipeline."""

from __future__ import annotations

import json
import logging
import os
from typing import TypedDict

from runtime.config.constants import DEFAULT_WORKFLOW_NAME, ENV_GCP_PROJECT, ENV_GCS_BUCKET

from cloud_bmt import config, core
from cloud_bmt.actions import gh_warning, write_github_output
from cloud_bmt.config import BmtConfig
from cloud_bmt.github import close_superseded_check_run
from cloud_bmt.pr_run_registry import claim_active_run, next_generation, read_record
from cloud_bmt.workflows_api import cancel_execution, start_execution

logger = logging.getLogger(__name__)


class WorkflowDispatchInvokePayload(TypedDict):
    """JSON-serializable argument passed to Workflows ``start_execution`` for BMT handoff."""

    workflow_run_id: str
    bucket: str
    repository: str
    head_sha: str
    head_branch: str
    head_event: str
    pr_number: str
    run_context: str
    accepted_projects: list[str]
    accepted_projects_json: str
    status_context: str
    force_pass: bool
    active_generation: int


def _workflow_execution_console_url(*, project: str, region: str, workflow_name: str, execution_name: str) -> str:
    execution_id = execution_name.rsplit("/", 1)[-1].strip()
    return (
        "https://console.cloud.google.com/workflows/workflow/"
        f"{region}/{workflow_name}/execution/{execution_id}?project={project}"
    )


def _accepted_projects(filtered_matrix_json: str) -> list[str]:
    payload = json.loads(filtered_matrix_json)
    include = payload.get("include", [])
    if not isinstance(include, list):
        raise TypeError("FILTERED_MATRIX_JSON must contain an 'include' array")
    accepted: list[str] = []
    seen: set[str] = set()
    for row in include:
        if not isinstance(row, dict):
            continue
        project = str(row.get("project", "")).strip()
        if project and project not in seen:
            seen.add(project)
            accepted.append(project)
    return accepted


def _supersede_prior_pr_run(
    *,
    cfg: BmtConfig,
    repository: str,
    pr_number: str,
    status_context: str,
) -> None:
    """Best-effort cancel prior cloud execution and close stale GitHub check."""
    bucket = cfg.gcs_bucket or core.require_env(ENV_GCS_BUCKET)
    prior, _ = read_record(bucket=bucket, repository=repository, pr_number=pr_number)
    if prior is None:
        return
    if prior.gcp_execution_name.strip():
        cancel_result = cancel_execution(execution_name=prior.gcp_execution_name)
        logger.info(
            "cancel_attempt pr_number=%s execution_name=%s cancel_result=%s prior_generation=%d",
            pr_number,
            prior.gcp_execution_name,
            cancel_result.value,
            prior.active_generation,
        )
    if prior.github_check_run_id is not None:
        try:
            close_superseded_check_run(
                repository=repository,
                check_run_id=prior.github_check_run_id,
                status_context=status_context,
            )
        except Exception:
            logger.warning(
                "close_superseded_check_failed pr_number=%s check_run_id=%s",
                pr_number,
                prior.github_check_run_id,
                exc_info=True,
            )


class WorkflowDispatchManager:
    def __init__(self, cfg: BmtConfig) -> None:
        self._cfg = cfg

    @classmethod
    def from_env(cls) -> WorkflowDispatchManager:
        return cls(config.get_config())

    def invoke(self, *, force_pass: bool = False) -> None:
        cfg = self._cfg
        github_output = core.require_env("GITHUB_OUTPUT")
        filtered_matrix_json = core.require_env("FILTERED_MATRIX_JSON")
        accepted_projects = _accepted_projects(filtered_matrix_json)
        if not accepted_projects:
            raise RuntimeError("No accepted projects were present in FILTERED_MATRIX_JSON")

        if force_pass:
            gh_warning(
                "force_pass: skipping Google Workflows execution; post BMT Gate success from handoff Plan instead."
            )
            write_github_output(
                github_output, "accepted_projects", json.dumps(accepted_projects, separators=(",", ":"))
            )
            write_github_output(github_output, "dispatch_confirmed", "false")
            write_github_output(github_output, "dispatch_reason", "ok_force_pass_cloud_skipped")
            return

        repository = (os.environ.get("GITHUB_REPOSITORY") or "").strip()
        head_sha = (os.environ.get("HEAD_SHA") or "").strip()
        pr_number = (os.environ.get("PR_NUMBER") or "").strip()
        workflow_run_id = core.workflow_run_id()
        active_generation = 0

        if pr_number.isdigit():
            _supersede_prior_pr_run(
                cfg=cfg,
                repository=repository,
                pr_number=pr_number,
                status_context=cfg.bmt_status_context,
            )
            prior, _ = read_record(
                bucket=cfg.gcs_bucket or core.require_env(ENV_GCS_BUCKET),
                repository=repository,
                pr_number=pr_number,
            )
            active_generation = next_generation(prior)

        payload: WorkflowDispatchInvokePayload = {
            "workflow_run_id": workflow_run_id,
            "bucket": cfg.gcs_bucket or core.require_env(ENV_GCS_BUCKET),
            "repository": repository,
            "head_sha": head_sha,
            "head_branch": (os.environ.get("HEAD_BRANCH") or "").strip(),
            "head_event": (os.environ.get("HEAD_EVENT") or "push").strip(),
            "pr_number": pr_number,
            "run_context": (os.environ.get("RUN_CONTEXT") or "ci").strip(),
            "accepted_projects": accepted_projects,
            "accepted_projects_json": json.dumps(accepted_projects, separators=(",", ":")),
            "status_context": cfg.bmt_status_context,
            "force_pass": force_pass,
            "active_generation": active_generation,
        }
        execution = start_execution(
            project=cfg.gcp_project or core.require_env(ENV_GCP_PROJECT),
            region=cfg.cloud_run_region,
            workflow_name=DEFAULT_WORKFLOW_NAME,
            argument=payload,
        )
        execution_name = str(execution.get("name") or "").strip()
        execution_state = str(execution.get("state") or "").strip()
        if not execution_name:
            raise RuntimeError("Workflow execution response did not include a name")

        if pr_number.isdigit():
            claim_active_run(
                bucket=cfg.gcs_bucket or core.require_env(ENV_GCS_BUCKET),
                repository=repository,
                pr_number=pr_number,
                active_commit=head_sha,
                github_workflow_run_id=workflow_run_id,
                gcp_execution_name=execution_name,
            )

        execution_url = _workflow_execution_console_url(
            project=cfg.gcp_project or core.require_env(ENV_GCP_PROJECT),
            region=cfg.cloud_run_region,
            workflow_name=DEFAULT_WORKFLOW_NAME,
            execution_name=execution_name,
        )

        write_github_output(github_output, "accepted_projects", payload["accepted_projects_json"])
        write_github_output(github_output, "workflow_execution_name", execution_name)
        write_github_output(github_output, "workflow_execution_url", execution_url)
        write_github_output(github_output, "workflow_execution_state", execution_state or "UNKNOWN")
        write_github_output(github_output, "dispatch_confirmed", "true")
        if force_pass:
            gh_warning("force_pass is active; this path should not run after handoff Plan skip.")
            write_github_output(github_output, "dispatch_reason", "ok_workflow_execution_started_force_pass")
        else:
            write_github_output(github_output, "dispatch_reason", "ok_workflow_execution_started")
