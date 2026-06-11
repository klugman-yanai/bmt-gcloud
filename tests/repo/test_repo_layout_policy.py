from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.repo import repo_layout_policy as policy


def _write_project(root: Path, name: str, project: str, *, template: bool = False) -> Path:
    project_root = root / name
    project_root.mkdir()
    data: dict[str, object] = {
        "schema_version": 1,
        "project": project,
        "description": f"{project} project",
    }
    if template:
        data["template"] = True
    data["bmts"] = {"smoke": {"enabled": False}}
    (project_root / "project.bmt.json").write_text(json.dumps(data), encoding="utf-8")
    return project_root


def _write_required_layout(root: Path) -> None:
    (root / ".github" / "workflows").mkdir(parents=True)
    for rel in ("AGENTS.md", "CLAUDE.md", "README.md", "Justfile", "pyproject.toml", "pyrightconfig.json"):
        (root / rel).write_text("", encoding="utf-8")
    (root / "projects").mkdir(parents=True, exist_ok=True)
    project_root = _write_project(root / "projects", "demo", "demo")
    (project_root / "plugin.py").write_text("# plugin\n", encoding="utf-8")
    examples_root = _write_project(root, "examples", "template", template=True)
    (examples_root / "plugin.py").write_text("# plugin\n", encoding="utf-8")

    (root / ".github" / "actions" / "setup-bmt-pex").mkdir(parents=True)
    (root / ".github" / "actions" / "setup-bmt-pex" / "action.yml").write_text("", encoding="utf-8")
    for rel in ("runtime", "ci", "sdk", "tests", "tools/scripts/hooks", "docs"):
        (root / rel).mkdir(parents=True, exist_ok=True)
    (root / "docs" / "README.md").write_text("", encoding="utf-8")
    (root / "sdk" / "bmt_sdk").mkdir(parents=True, exist_ok=True)
    (root / "sdk" / "bmt_sdk" / "py.typed").write_text("", encoding="utf-8")
    (root / "tools" / "scripts" / "hooks" / "pre-commit-sync-gcp.sh").write_text("", encoding="utf-8")
    (root / ".github" / "workflows" / "bmt-handoff.yml").write_text("", encoding="utf-8")
    (root / ".github" / "workflows" / "build-and-test.yml").write_text("", encoding="utf-8")


def _patch_policy_paths(monkeypatch: pytest.MonkeyPatch, root: Path, tracked: list[str]) -> None:
    monkeypatch.setattr(policy, "suite_root", lambda: root)
    monkeypatch.setattr(policy, "repo_root", lambda: root)
    monkeypatch.setattr(policy, "_tracked_paths", lambda _root: tracked)
    monkeypatch.setattr(policy, "_ignored_paths", lambda _root, _paths: [])


def test_repo_layout_policy_accepts_standalone_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_required_layout(tmp_path)
    tracked = [
        "AGENTS.md",
        "CLAUDE.md",
        "README.md",
        "Justfile",
        "pyproject.toml",
        "pyrightconfig.json",
        ".github/workflows/build-and-test.yml",
        "sdk/bmt_sdk/py.typed",
        "runtime/__init__.py",
        "projects/demo/project.bmt.json",
        "examples/project.bmt.json",
    ]
    _patch_policy_paths(monkeypatch, tmp_path, tracked)

    assert policy.RepoLayoutPolicy().run() == 0


@pytest.mark.parametrize(
    "tracked",
    [
        ["plugins/projects/demo/project.json"],
        ["generated/stage/projects/demo/project.json"],
    ],
)
def test_repo_layout_policy_rejects_legacy_or_generated_tracked_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tracked: list[str]
) -> None:
    _write_required_layout(tmp_path)
    _patch_policy_paths(monkeypatch, tmp_path, tracked)

    assert policy.RepoLayoutPolicy().run() == 1


def test_repo_layout_policy_requires_template_marker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_required_layout(tmp_path)
    (tmp_path / "examples" / "project.bmt.json").write_text(
        json.dumps({"schema_version": 1, "project": "template", "bmts": {"example": {"enabled": False}}}),
        encoding="utf-8",
    )
    _patch_policy_paths(monkeypatch, tmp_path, ["examples/project.bmt.json"])

    assert policy.RepoLayoutPolicy().run() == 1


def test_repo_layout_policy_rejects_project_local_pyproject(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_required_layout(tmp_path)
    (tmp_path / "projects" / "demo" / "pyproject.toml").write_text("", encoding="utf-8")
    _patch_policy_paths(monkeypatch, tmp_path, ["projects/demo/project.bmt.json", "projects/demo/pyproject.toml"])

    assert policy.RepoLayoutPolicy().run() == 1


def test_repo_layout_policy_rejects_invalid_python_dependencies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_required_layout(tmp_path)
    (tmp_path / "projects" / "demo" / "project.bmt.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project": "demo",
                "python_dependencies": ["ok>=1", ""],
                "bmts": {"smoke": {"enabled": False}},
            }
        ),
        encoding="utf-8",
    )
    _patch_policy_paths(monkeypatch, tmp_path, ["projects/demo/project.bmt.json"])

    assert policy.RepoLayoutPolicy().run() == 1


def test_repo_layout_policy_rejects_legacy_cloud_bmt_top_level(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_required_layout(tmp_path)
    (tmp_path / "demo-cloud-bmt").mkdir()
    _patch_policy_paths(monkeypatch, tmp_path, ["demo-cloud-bmt/project.json"])

    assert policy.RepoLayoutPolicy().run() == 1


def test_repo_layout_policy_rejects_legacy_shell_bmt_top_level(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_required_layout(tmp_path)
    (tmp_path / "bmt" / "DEMO").mkdir(parents=True)
    _patch_policy_paths(monkeypatch, tmp_path, ["projects/demo/project.bmt.json"])

    assert policy.RepoLayoutPolicy().run() == 1


def test_repo_layout_policy_rejects_ignored_required_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_required_layout(tmp_path)
    demo_plugin = tmp_path / "projects" / "demo" / "plugin.py"
    demo_plugin.write_text("", encoding="utf-8")
    _patch_policy_paths(monkeypatch, tmp_path, ["projects/demo/plugin.py"])
    monkeypatch.setattr(policy, "_ignored_paths", lambda _root, _paths: ["projects/demo/plugin.py"])

    assert policy.RepoLayoutPolicy().run() == 1
