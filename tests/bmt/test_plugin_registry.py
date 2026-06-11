from __future__ import annotations

import json
from pathlib import Path

import pytest
from bmt_sdk.worker import AbiIncompatibleError

from runtime.plugin_registry import load_stage_plugin_index, resolve_plugin_descriptor


def _write_index(project_dir: Path, *, api_version: str = "2.0") -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "plugin-index.json").write_text(
        json.dumps(
            {
                "plugins": [
                    {
                        "plugin_id": "sk.default",
                        "plugin_slug": "default",
                        "project": "sk",
                        "plugin_version": "2.0.0",
                        "plugin_api_version": api_version,
                        "entrypoint": "sk_plugin.worker:Worker",
                        "capabilities": {"network_profile": "none"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_load_stage_plugin_index_returns_entries(tmp_path: Path) -> None:
    _write_index(tmp_path / "projects" / "sk")
    plugins = load_stage_plugin_index(stage_root=tmp_path, project="sk")
    assert len(plugins) == 1
    assert plugins[0].plugin_id == "sk.default"


def test_resolve_plugin_descriptor_validates_abi(tmp_path: Path) -> None:
    _write_index(tmp_path / "projects" / "sk", api_version="3.0")
    with pytest.raises(AbiIncompatibleError):
        resolve_plugin_descriptor(
            stage_root=tmp_path,
            project="sk",
            plugin_id="sk.default",
            plugin_version="2.0.0",
        )
