from __future__ import annotations

from pathlib import Path

import pytest

from tests.bmt.conftest_scaffold import seed_examples_template
from tools.bmt.plugin_package_scaffold import add_plugin_package
from tools.bmt.plugin_registry_validate import validate_plugin_registry
from tools.bmt.scaffold import add_project


def _load_registry(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml

        data = yaml.safe_load(text)
    except ModuleNotFoundError:
        import json

        data = json.loads(text)
    assert isinstance(data, dict)
    return data


def test_add_plugin_package_creates_package_and_registry(tmp_path: Path) -> None:
    seed_examples_template(tmp_path)
    add_project("acme", source_root=tmp_path, dry_run=False)

    rc = add_plugin_package("acme", "keyword", source_root=tmp_path)

    assert rc == 0
    plugin_dir = tmp_path / "projects" / "acme" / "plugins" / "keyword"
    assert (plugin_dir / "plugin.toml").is_file()
    worker_py = plugin_dir / "src" / "acme_keyword" / "worker.py"
    assert worker_py.is_file()
    worker_source = worker_py.read_text(encoding="utf-8")
    assert "prepared = _prepared_assets_from_request(request)" in worker_source
    assert "def _prepared_assets_from_request(request: ExecuteRequest) -> PreparedAssets:" in worker_source
    registry = _load_registry(tmp_path / "projects" / "acme" / "plugins" / "registry.yaml")
    assert registry["plugins"][0]["plugin_id"] == "acme.keyword"


def test_validate_plugin_registry_checks_duplicate_ids(tmp_path: Path) -> None:
    seed_examples_template(tmp_path)
    add_project("acme", source_root=tmp_path, dry_run=False)
    add_plugin_package("acme", "keyword", source_root=tmp_path)
    registry_path = tmp_path / "projects" / "acme" / "plugins" / "registry.yaml"
    registry = _load_registry(registry_path)
    registry["plugins"].append(registry["plugins"][0])
    try:
        import yaml

        registry_path.write_text(yaml.safe_dump(registry), encoding="utf-8")
    except ModuleNotFoundError:
        import json

        registry_path.write_text(json.dumps(registry), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate plugin_id"):
        validate_plugin_registry("acme", source_root=tmp_path)
