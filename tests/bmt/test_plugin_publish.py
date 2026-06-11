from __future__ import annotations

from pathlib import Path

import pytest

from tools.bmt.publisher import publish_bmt
from tools.bmt.scaffold import add_bmt, add_project

pytestmark = pytest.mark.integration


def test_publish_bmt_materializes_root_project_and_syncs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_root = tmp_path / "suite"
    stage_root = tmp_path / "generated" / "stage"
    source_root.mkdir()
    add_project("acme", source_root=source_root, dry_run=False)
    add_bmt("acme", "wake_word_quality", source_root=source_root)

    synced: list[str] = []

    def _fake_sync(*, bucket: str, project: str, stage_root: Path | None = None) -> int:
        assert stage_root == stage_root_arg
        assert bucket == "demo-bucket"
        synced.append(project)
        return 0

    stage_root_arg = stage_root
    monkeypatch.setenv("GCS_BUCKET", "demo-bucket")
    monkeypatch.setattr("tools.bmt.publisher.sync_project", _fake_sync)

    result = publish_bmt(source_root=source_root, stage_root=stage_root, project="acme", bmt_slug="wake_word_quality")

    assert result.source_dir == source_root / "projects" / "acme"
    assert result.stage_dir == stage_root / "projects" / "acme"
    assert result.stage_dir.is_dir()
    assert (result.stage_dir / "plugin.py").is_file()
    assert (result.stage_dir / "wake_word_quality.json").is_file()
    assert synced == ["acme"]


def test_publish_bmt_can_skip_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_root = tmp_path / "suite"
    stage_root = tmp_path / "generated" / "stage"
    source_root.mkdir()
    add_project("acme", source_root=source_root, dry_run=False)
    add_bmt("acme", "wake_word_quality", source_root=source_root)

    called = False

    def _fake_sync(**_: object) -> int:
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr("tools.bmt.publisher.sync_project", _fake_sync)

    publish_bmt(
        source_root=source_root, stage_root=stage_root, project="acme", bmt_slug="wake_word_quality", sync=False
    )

    assert called is False


def test_publish_bmt_fails_before_sync_when_direct_plugin_is_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "suite"
    stage_root = tmp_path / "generated" / "stage"
    source_root.mkdir()
    add_project("acme", source_root=source_root, dry_run=False)
    add_bmt("acme", "wake_word_quality", source_root=source_root)

    plugin_file = source_root / "projects" / "acme" / "plugin.py"
    plugin_file.write_text("not valid python(", encoding="utf-8")

    called = False

    def _fake_sync(**_: object) -> int:
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr("tools.bmt.publisher.sync_project", _fake_sync)

    with pytest.raises(SyntaxError, match="was never closed"):
        publish_bmt(source_root=source_root, stage_root=stage_root, project="acme", bmt_slug="wake_word_quality")

    assert called is False
    assert not (stage_root / "projects" / "acme").exists()
