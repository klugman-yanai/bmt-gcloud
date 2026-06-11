from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from runtime.github.github_auth import get_installation_token_from_app


def test_get_installation_token_returns_none_on_github_exception() -> None:
    with patch("runtime.github.github_auth.GithubIntegration") as m:
        inst = MagicMock()
        inst.get_access_token.side_effect = GithubException(500, "err", None)
        m.return_value = inst
        assert get_installation_token_from_app("1", "2", "fake-pem-key") is None
