"""Tests for cancel_execution retry and benign terminal handling."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests.exceptions
from cloud_bmt.workflows_api import CancelResult, WorkflowsApiError, cancel_execution

pytestmark = pytest.mark.unit


class _Resp:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.ok = status_code < 400
        self.text = text

    def json(self) -> dict[str, str]:
        return {}


def test_cancel_success(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    session.post.return_value = _Resp(200)
    monkeypatch.setattr("cloud_bmt.workflows_api._session", lambda: session)

    assert cancel_execution(execution_name="projects/p/locations/r/workflows/w/executions/e1") == CancelResult.SUCCESS


def test_cancel_benign_404(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    session.post.return_value = _Resp(404, "not found")
    monkeypatch.setattr("cloud_bmt.workflows_api._session", lambda: session)

    assert cancel_execution(execution_name="projects/p/locations/r/workflows/w/executions/e1") == CancelResult.BENIGN_TERMINAL


def test_cancel_retries_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = {"n": 0}

    def _session() -> MagicMock:
        call_count["n"] += 1
        session = MagicMock()
        if call_count["n"] < 2:
            session.post.side_effect = requests.exceptions.ConnectionError("net")
        else:
            session.post.return_value = _Resp(200)
        return session

    monkeypatch.setattr("cloud_bmt.workflows_api._session", _session)
    monkeypatch.setattr("time.sleep", lambda _: None)

    assert cancel_execution(execution_name="projects/p/locations/r/workflows/w/executions/e1") == CancelResult.SUCCESS
    assert call_count["n"] == 2


def test_cancel_empty_name_is_benign() -> None:
    assert cancel_execution(execution_name="") == CancelResult.BENIGN_TERMINAL


def test_cancel_raises_on_persistent_error(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    session.post.return_value = _Resp(403, "denied")
    monkeypatch.setattr("cloud_bmt.workflows_api._session", lambda: session)

    with pytest.raises(WorkflowsApiError, match="403"):
        cancel_execution(execution_name="projects/p/locations/r/workflows/w/executions/e1")
