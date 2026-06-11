from __future__ import annotations

from pathlib import Path

import pytest

from runtime.plugin_publisher import plugin_digest

pytestmark = pytest.mark.unit


def test_plugin_digest_tracks_worker_source_changes(tmp_path: Path) -> None:
    project_root = tmp_path / "acme"
    worker_py = project_root / "plugins" / "keyword" / "src" / "acme_keyword" / "worker.py"
    worker_py.parent.mkdir(parents=True)
    (project_root / "plugin.py").write_text("def plugin(): return object()\n", encoding="utf-8")
    worker_py.write_text("VALUE = 1\n", encoding="utf-8")

    digest_before = plugin_digest(project_root)
    worker_py.write_text("VALUE = 2\n", encoding="utf-8")
    digest_after = plugin_digest(project_root)

    assert digest_before != digest_after
