"""PR-scoped active run registry in GCS (CAS writes)."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

import whenever

from cloud_bmt.gcs import GcsError, download_json, read_object_with_generation, upload_json_if_generation

logger = logging.getLogger(__name__)

PrActiveStatus = Literal["running", "superseded", "finished", "cancel_failed"]

_MAX_CAS_ATTEMPTS = 5
_REPO_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


@dataclass(frozen=True, slots=True)
class PrActiveRecord:
    pr_number: str
    active_generation: int
    active_commit: str
    github_workflow_run_id: str
    gcp_execution_name: str
    github_check_run_id: int | None
    status: PrActiveStatus
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PrActiveRecord:
        check_raw = payload.get("github_check_run_id")
        check_id: int | None
        if check_raw is None or check_raw == "":
            check_id = None
        else:
            check_id = int(check_raw)
        status = str(payload.get("status") or "running")
        if status not in ("running", "superseded", "finished", "cancel_failed"):
            status = "running"
        return cls(
            pr_number=str(payload.get("pr_number") or ""),
            active_generation=int(payload.get("active_generation") or 0),
            active_commit=str(payload.get("active_commit") or ""),
            github_workflow_run_id=str(payload.get("github_workflow_run_id") or ""),
            gcp_execution_name=str(payload.get("gcp_execution_name") or ""),
            github_check_run_id=check_id,
            status=status,  # type: ignore[arg-type]
            updated_at=str(payload.get("updated_at") or ""),
        )


def _sanitize_repo_segment(repository: str) -> tuple[str, str]:
    owner, _, repo = repository.strip().partition("/")
    if not owner or not repo:
        raise ValueError(f"Invalid repository {repository!r}")
    safe_owner = _REPO_SAFE.sub("_", owner)
    safe_repo = _REPO_SAFE.sub("_", repo)
    return safe_owner, safe_repo


def registry_object_uri(*, bucket: str, repository: str, pr_number: str) -> str:
    owner, repo = _sanitize_repo_segment(repository)
    pr = str(pr_number).strip()
    if not pr.isdigit():
        raise ValueError(f"pr_number must be digits, got {pr_number!r}")
    return f"gs://{bucket}/triggers/pr-active/{owner}/{repo}/pr-{pr}.json"


def read_record(*, bucket: str, repository: str, pr_number: str) -> tuple[PrActiveRecord | None, int | None]:
    uri = registry_object_uri(bucket=bucket, repository=repository, pr_number=pr_number)
    raw, generation = read_object_with_generation(uri)
    if generation is None or not raw:
        return None, None
    payload, err = download_json(uri)
    if err or payload is None:
        logger.warning("pr_registry_read_invalid uri=%s err=%s", uri, err)
        return None, generation
    return PrActiveRecord.from_dict(payload), generation


def cas_write_record(
    *,
    bucket: str,
    repository: str,
    record: PrActiveRecord,
    expected_generation: int | None,
) -> int:
    uri = registry_object_uri(bucket=bucket, repository=repository, pr_number=record.pr_number)
    return upload_json_if_generation(uri, record.to_dict(), expected_generation=expected_generation)


def next_generation(prior: PrActiveRecord | None) -> int:
    if prior is None or prior.active_generation < 1:
        return 1
    return prior.active_generation + 1


def now_iso() -> str:
    return whenever.Instant.now().format_iso(unit="second")


@dataclass(frozen=True, slots=True)
class ClaimResult:
    record: PrActiveRecord
    prior: PrActiveRecord | None
    gcs_generation: int


def claim_active_run(
    *,
    bucket: str,
    repository: str,
    pr_number: str,
    active_commit: str,
    github_workflow_run_id: str,
    gcp_execution_name: str,
) -> ClaimResult:
    """CAS loop: bump generation and write new active run record."""
    last_exc: GcsError | None = None
    for attempt in range(1, _MAX_CAS_ATTEMPTS + 1):
        prior, expected_gen = read_record(bucket=bucket, repository=repository, pr_number=pr_number)
        generation = next_generation(prior)
        record = PrActiveRecord(
            pr_number=str(pr_number),
            active_generation=generation,
            active_commit=active_commit,
            github_workflow_run_id=github_workflow_run_id,
            gcp_execution_name=gcp_execution_name,
            github_check_run_id=None,
            status="running",
            updated_at=now_iso(),
        )
        try:
            new_gen = cas_write_record(
                bucket=bucket,
                repository=repository,
                record=record,
                expected_generation=expected_gen,
            )
            logger.info(
                "pr_registry_claimed pr_number=%s generation=%d workflow_run_id=%s gcs_generation=%d attempt=%d",
                pr_number,
                generation,
                github_workflow_run_id,
                new_gen,
                attempt,
            )
            return ClaimResult(record=record, prior=prior, gcs_generation=new_gen)
        except GcsError as exc:
            last_exc = exc
            logger.warning(
                "pr_registry_cas_conflict pr_number=%s attempt=%d/%d",
                pr_number,
                attempt,
                _MAX_CAS_ATTEMPTS,
            )
    raise GcsError(f"CAS claim failed for PR {pr_number} after {_MAX_CAS_ATTEMPTS} attempts") from last_exc


def patch_check_run_id(
    *,
    bucket: str,
    repository: str,
    pr_number: str,
    github_workflow_run_id: str,
    github_check_run_id: int,
) -> None:
    """After plan creates a check, persist check_run_id for dispatch-time stale close."""
    for _attempt in range(1, _MAX_CAS_ATTEMPTS + 1):
        record, expected_gen = read_record(bucket=bucket, repository=repository, pr_number=pr_number)
        if record is None or record.github_workflow_run_id != github_workflow_run_id:
            logger.info(
                "pr_registry_patch_check_skipped pr_number=%s workflow_run_id=%s reason=not_active",
                pr_number,
                github_workflow_run_id,
            )
            return
        updated = PrActiveRecord(
            pr_number=record.pr_number,
            active_generation=record.active_generation,
            active_commit=record.active_commit,
            github_workflow_run_id=record.github_workflow_run_id,
            gcp_execution_name=record.gcp_execution_name,
            github_check_run_id=github_check_run_id,
            status=record.status,
            updated_at=now_iso(),
        )
        try:
            cas_write_record(
                bucket=bucket,
                repository=repository,
                record=updated,
                expected_generation=expected_gen,
            )
            logger.info(
                "pr_registry_check_patched pr_number=%s generation=%d check_run_id=%d",
                pr_number,
                record.active_generation,
                github_check_run_id,
            )
            return
        except GcsError as exc:
            last_exc = exc
    raise GcsError(f"CAS patch check_run_id failed for PR {pr_number}") from last_exc
