"""List OEM release tags from GitHub (core-main)."""

from __future__ import annotations

import os

from runtime.baseline.tags import newest_release_tag_for_prefix, tag_prefix_for_gate_project


def list_core_main_release_tags(*, repository: str | None = None, token: str | None = None) -> list[str]:
    """Return all tag names on the firmware repository."""
    repo = (repository or os.environ.get("CORE_MAIN_REPOSITORY") or "Cloud Bench-org/core-main").strip()
    tok = (token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if not tok:
        return []
    try:
        from github import Auth, Github
    except ImportError:
        return []
    gh = Github(auth=Auth.Token(tok))
    names: list[str] = []
    try:
        for tag in gh.get_repo(repo).get_tags():
            name = getattr(tag, "name", None)
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
    except Exception:
        return []
    return names


def newest_mapped_tag_for_project(gate_project: str, *, repository: str | None = None) -> str | None:
    prefix = tag_prefix_for_gate_project(gate_project)
    if prefix is None:
        return None
    tags = list_core_main_release_tags(repository=repository)
    return newest_release_tag_for_prefix(tags, prefix)
