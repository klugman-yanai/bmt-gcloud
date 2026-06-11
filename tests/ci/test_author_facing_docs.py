"""Guard author-facing docs against stale plugin API references."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools.repo.paths import suite_root

pytestmark = pytest.mark.unit

_STALE_PATTERNS = (
    re.compile(r"Cloud BenchProjectSettings"),
    re.compile(r"Cloud BenchRunnerPlugin"),
    re.compile(r"cloud_bench_plugin\.py"),
    re.compile(r"\bRunnerPlugin\b(?!Spec)"),
    re.compile(r"plugin-config-model\.md"),
    re.compile(r"plugin-author-contract\.md"),
    re.compile(r"plugin-sdk-architecture\.md"),
    re.compile(r"plugin-types\.md"),
)

_AUTHOR_DOC_PATHS = (
    suite_root() / "README.md",
    suite_root() / "docs" / "README.md",
    suite_root() / "docs" / "plugins.md",
    suite_root() / "examples" / "README.md",
    suite_root() / "cloud-ci-handoff" / "docs" / "README.md",
    suite_root() / "cloud-ci-handoff" / "docs" / "adding-a-project.md",
    suite_root() / "cloud-ci-handoff" / "docs" / "plugin-conformance-checklist.md",
    suite_root() / "cloud-ci-handoff" / "sdk" / "README.md",
    suite_root() / "AGENTS.md",
)


def _author_doc_files() -> list[Path]:
    files = list(_AUTHOR_DOC_PATHS)
    files.extend(suite_root().glob("projects/*/README.md"))
    return files


def test_author_facing_docs_avoid_stale_plugin_api_references() -> None:
    violations: list[str] = []
    for path in _author_doc_files():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(suite_root())
        for pattern in _STALE_PATTERNS:
            if pattern.search(text):
                violations.append(f"{rel}: matched {pattern.pattern}")
    assert not violations, "Stale plugin API references:\n" + "\n".join(violations)
