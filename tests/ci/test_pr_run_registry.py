"""Tests for PR active run registry (CAS)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from cloud_bmt.gcs import GcsError
from cloud_bmt.pr_run_registry import (
    PrActiveRecord,
    cas_write_record,
    claim_active_run,
    next_generation,
    registry_object_uri,
)

pytestmark = pytest.mark.unit


def test_registry_object_uri_sanitizes_repo() -> None:
    uri = registry_object_uri(bucket="b", repository="Org/Repo.Name", pr_number="42")
    assert uri == "gs://b/triggers/pr-active/Org/Repo.Name/pr-42.json"


def test_next_generation_starts_at_one() -> None:
    assert next_generation(None) == 1


def test_next_generation_increments() -> None:
    prior = PrActiveRecord(
        pr_number="1",
        active_generation=3,
        active_commit="sha",
        github_workflow_run_id="1",
        gcp_execution_name="exec",
        github_check_run_id=None,
        status="running",
        updated_at="2026-01-01T00:00:00Z",
    )
    assert next_generation(prior) == 4


def test_claim_active_run_writes_record(monkeypatch: pytest.MonkeyPatch) -> None:
    writes: list[tuple[int | None, PrActiveRecord]] = []

    def _read(**kwargs: object) -> tuple[PrActiveRecord | None, int | None]:
        return None, None

    def _cas(**kwargs: object) -> int:
        record = kwargs["record"]
        assert isinstance(record, PrActiveRecord)
        writes.append((kwargs.get("expected_generation"), record))
        return 99

    monkeypatch.setattr("cloud_bmt.pr_run_registry.read_record", _read)
    monkeypatch.setattr("cloud_bmt.pr_run_registry.cas_write_record", _cas)

    result = claim_active_run(
        bucket="b",
        repository="o/r",
        pr_number="7",
        active_commit="abc",
        github_workflow_run_id="99",
        gcp_execution_name="projects/p/executions/x",
    )
    assert result.record.active_generation == 1
    assert result.record.github_workflow_run_id == "99"
    assert writes[0][0] is None


def test_claim_active_run_retries_on_cas_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"n": 0}

    def _read(**kwargs: object) -> tuple[PrActiveRecord | None, int | None]:
        if attempts["n"] == 0:
            return None, None
        prior = PrActiveRecord(
            pr_number="7",
            active_generation=1,
            active_commit="old",
            github_workflow_run_id="1",
            gcp_execution_name="e1",
            github_check_run_id=None,
            status="running",
            updated_at="2026-01-01T00:00:00Z",
        )
        return prior, 10

    def _cas(**kwargs: object) -> int:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise GcsError("conflict")
        return 11

    monkeypatch.setattr("cloud_bmt.pr_run_registry.read_record", _read)
    monkeypatch.setattr("cloud_bmt.pr_run_registry.cas_write_record", _cas)

    result = claim_active_run(
        bucket="b",
        repository="o/r",
        pr_number="7",
        active_commit="abc",
        github_workflow_run_id="99",
        gcp_execution_name="exec",
    )
    assert result.record.active_generation == 2
    assert attempts["n"] == 2


def test_cas_write_record_delegates_to_gcs(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_upload = MagicMock(return_value=5)
    monkeypatch.setattr("cloud_bmt.pr_run_registry.upload_json_if_generation", mock_upload)
    record = PrActiveRecord(
        pr_number="1",
        active_generation=1,
        active_commit="sha",
        github_workflow_run_id="1",
        gcp_execution_name="e",
        github_check_run_id=None,
        status="running",
        updated_at="2026-01-01T00:00:00Z",
    )
    gen = cas_write_record(bucket="b", repository="o/r", record=record, expected_generation=0)
    assert gen == 5
    mock_upload.assert_called_once()
