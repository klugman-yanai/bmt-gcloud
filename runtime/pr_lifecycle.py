"""PR-first lifecycle: registry authority checks for runtime modes."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from runtime.config.decisions import ReasonCode
from runtime.models import ExecutionPlan

logger = logging.getLogger(__name__)

_REPO_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def pr_lifecycle_applies(*, plan: ExecutionPlan) -> bool:
    """PR lifecycle (registry, supersede guards) applies when plan carries a PR number."""
    return plan.pr_number.isdigit()


def _registry_relative_path(*, repository: str, pr_number: str) -> Path:
    owner, _, repo = repository.strip().partition("/")
    if not owner or not repo:
        raise ValueError(f"Invalid repository {repository!r}")
    safe_owner = _REPO_SAFE.sub("_", owner)
    safe_repo = _REPO_SAFE.sub("_", repo)
    return Path("triggers") / "pr-active" / safe_owner / safe_repo / f"pr-{pr_number}.json"


def _load_registry_record(*, stage_root: Path, repository: str, pr_number: str) -> dict[str, object] | None:
    path = stage_root / _registry_relative_path(repository=repository, pr_number=pr_number)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("pr_lifecycle_registry_invalid path=%s", path)
        return None
    return payload if isinstance(payload, dict) else None


def is_authoritative_for_pr(*, plan: ExecutionPlan, stage_root: Path) -> bool:
    """Return False when this run is superseded by a newer PR generation."""
    if not pr_lifecycle_applies(plan=plan):
        return True
    record = _load_registry_record(stage_root=stage_root, repository=plan.repository, pr_number=plan.pr_number)
    if record is None:
        logger.info(
            "bmt_run_authoritative_missing_registry workflow_run_id=%s pr_number=%s",
            plan.workflow_run_id,
            plan.pr_number,
        )
        return True
    reg_run_id = str(record.get("github_workflow_run_id") or "")
    reg_gen = int(record.get("active_generation") or 0)
    if reg_run_id == plan.workflow_run_id and reg_gen == plan.active_generation:
        return True
    logger.info(
        "bmt_run_superseded workflow_run_id=%s pr_number=%s generation=%d registry_run_id=%s "
        "registry_generation=%d reason_code=%s superseded=true",
        plan.workflow_run_id,
        plan.pr_number,
        plan.active_generation,
        reg_run_id,
        reg_gen,
        ReasonCode.SUPERSEDED.value,
    )
    return False


def patch_registry_check_run_id(*, plan: ExecutionPlan, stage_root: Path, check_run_id: int) -> None:
    """Persist check_run_id on the PR registry record for dispatch-time stale close."""
    if not pr_lifecycle_applies(plan=plan):
        return
    path = stage_root / _registry_relative_path(repository=plan.repository, pr_number=plan.pr_number)
    if not path.is_file():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("pr_lifecycle_registry_patch_invalid path=%s", path)
        return
    if not isinstance(payload, dict):
        return
    if str(payload.get("github_workflow_run_id") or "") != plan.workflow_run_id:
        return
    payload["github_check_run_id"] = check_run_id
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    logger.info(
        "pr_registry_check_patched_runtime pr_number=%s check_run_id=%d workflow_run_id=%s",
        plan.pr_number,
        check_run_id,
        plan.workflow_run_id,
    )
