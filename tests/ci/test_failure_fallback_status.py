"""Unit tests for fallback terminal status emission (Python bmt post-handoff-timeout-status)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ci.cloud_bmt.handoff import HandoffManager
from tests.support.fixtures.ci import mock_config, mock_github_api

__all__ = ["mock_config", "mock_github_api"]  # re-export for pytest fixture discovery

pytestmark = pytest.mark.unit


def test_post_handoff_timeout_status_posts_when_not_terminal(
    monkeypatch: pytest.MonkeyPatch,
    mock_github_api: MagicMock,
    mock_config: MagicMock,
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("HEAD_SHA", "abc123")
    mock_github_api.should_post_failure_status.return_value = True

    HandoffManager.from_env().post_handoff_timeout_status()

    mock_github_api.should_post_failure_status.assert_called_once_with("owner/repo", "abc123", "BMT Gate")
    mock_github_api.post_commit_status.assert_called_once_with(
        "owner/repo", "abc123", "error", "BMT Gate", "BMT failed to complete handshake."
    )


def test_post_handoff_timeout_status_skips_when_terminal(
    monkeypatch: pytest.MonkeyPatch,
    mock_github_api: MagicMock,
    mock_config: MagicMock,
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("HEAD_SHA", "abc123")
    mock_github_api.should_post_failure_status.return_value = False

    HandoffManager.from_env().post_handoff_timeout_status()

    mock_github_api.should_post_failure_status.assert_called_once()
    mock_github_api.post_commit_status.assert_not_called()


def test_post_handoff_timeout_status_missing_env_skips(
    monkeypatch: pytest.MonkeyPatch,
    mock_github_api: MagicMock,
    mock_config: MagicMock,
) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("HEAD_SHA", raising=False)
    monkeypatch.delenv("REPOSITORY", raising=False)

    HandoffManager.from_env().post_handoff_timeout_status()

    mock_github_api.should_post_failure_status.assert_not_called()
    mock_github_api.post_commit_status.assert_not_called()


def test_post_infra_skip_status_posts_success(
    monkeypatch: pytest.MonkeyPatch,
    mock_github_api: MagicMock,
    mock_config: MagicMock,
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("HEAD_SHA", "abc123")

    HandoffManager.from_env().post_infra_skip_status("PEX unavailable")

    mock_github_api.post_commit_status.assert_called_once_with(
        "owner/repo",
        "abc123",
        "success",
        "BMT Gate",
        "BMT skipped (infra: PEX unavailable)",
    )


def test_post_infra_skip_status_truncates_long_reason(
    monkeypatch: pytest.MonkeyPatch,
    mock_github_api: MagicMock,
    mock_config: MagicMock,
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("HEAD_SHA", "abc123")
    long_reason = "x" * 200

    HandoffManager.from_env().post_infra_skip_status(long_reason)

    args = mock_github_api.post_commit_status.call_args[0]
    assert args[2] == "success"
    assert len(args[4]) <= 140
    assert args[4].startswith("BMT skipped (infra: ")


def test_post_infra_skip_status_missing_env_skips(
    monkeypatch: pytest.MonkeyPatch,
    mock_github_api: MagicMock,
    mock_config: MagicMock,
) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("HEAD_SHA", raising=False)
    monkeypatch.delenv("REPOSITORY", raising=False)

    HandoffManager.from_env().post_infra_skip_status("PEX unavailable")

    mock_github_api.post_commit_status.assert_not_called()
