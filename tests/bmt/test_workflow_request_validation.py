from __future__ import annotations

import pytest
from pydantic import ValidationError

from runtime.models import WorkflowRequest


def test_repository_empty_allowed() -> None:
    w = WorkflowRequest(workflow_run_id="x", repository="", head_sha="")
    assert w.repository == ""


def test_repository_invalid_shape_rejected() -> None:
    with pytest.raises(ValidationError):
        WorkflowRequest(workflow_run_id="x", repository="nope", head_sha="")


def test_head_sha_invalid_rejected() -> None:
    with pytest.raises(ValidationError):
        WorkflowRequest(workflow_run_id="x", repository="", head_sha="not-hex")


def test_head_sha_valid_normalized() -> None:
    w = WorkflowRequest(workflow_run_id="x", repository="", head_sha="Aa" * 20)
    assert w.head_sha == "aa" * 20
