from __future__ import annotations

import json
from pathlib import Path

from tests.bmt.conftest_scaffold import seed_examples_template
from tools.bmt.scaffold import add_bmt, add_project


def test_add_project_creates_stage_scaffold(tmp_path: Path) -> None:
    source_root = tmp_path
    seed_examples_template(source_root)

    rc = add_project("acme", source_root=source_root, dry_run=False)

    assert rc == 0
    project_root = source_root / "projects" / "acme"
    assert (project_root / "project.bmt.json").is_file()
    assert (project_root / "README.md").is_file()
    assert (project_root / "plugin.py").is_file()

    project_manifest = json.loads((project_root / "project.bmt.json").read_text(encoding="utf-8"))
    assert project_manifest["project"] == "acme"
    assert "template" not in project_manifest


def test_add_bmt_creates_disabled_manifest(tmp_path: Path) -> None:
    source_root = tmp_path
    seed_examples_template(source_root)
    add_project("acme", source_root=source_root, dry_run=False)

    rc = add_bmt("acme", "wake_word_quality", source_root=source_root)

    assert rc == 0
    manifest_path = source_root / "projects" / "acme" / "project.bmt.json"
    bundle = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = bundle["bmts"]["wake_word_quality"]
    assert manifest["enabled"] is False
    assert manifest["tolerance_abs"] == 0.25
