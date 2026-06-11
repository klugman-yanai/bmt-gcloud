"""Plugin execution context."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bmt_sdk.models import BmtManifestView, ProjectManifestView
from bmt_sdk.results import PreparedAssets


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Per-hook inputs: manifest config, dataset/workspace paths, runner binary, runtime sidecars."""

    project_manifest: ProjectManifestView
    bmt_manifest: BmtManifestView
    plugin_root: Path
    workspace_root: Path
    dataset_root: Path
    outputs_root: Path
    logs_root: Path
    runner_path: Path | None = None
    deps_root: Path | None = None
    case_progress_root: Path | None = None

    @property
    def plugin_config(self) -> Mapping[str, Any]:
        """Shortcut for plugin-owned manifest config with read-only type intent."""

        return self.bmt_manifest.plugin_config

    def ensure_output_dirs(self) -> None:
        """Create standard writable directories before a plugin writes artifacts or logs."""

        self.outputs_root.mkdir(parents=True, exist_ok=True)
        self.logs_root.mkdir(parents=True, exist_ok=True)

    def prepared_assets(self) -> PreparedAssets:
        """Return the standard :class:`bmt_sdk.results.PreparedAssets` for this context."""

        return PreparedAssets(
            dataset_root=self.dataset_root,
            workspace_root=self.workspace_root,
            runner_path=self.runner_path,
        )

    def iter_input_files(self, *, include_dataset_manifest: bool = False) -> Iterator[Path]:
        """Yield dataset files in stable order, skipping ``dataset_manifest.json`` by default."""

        for path in sorted(self.dataset_root.rglob("*")):
            if not path.is_file():
                continue
            if not include_dataset_manifest and path.name == "dataset_manifest.json":
                continue
            yield path
