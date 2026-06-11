"""Load a plugin instance from plugin.py by convention."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from bmt_sdk.discovery import load_plugin_from_module
from bmt_sdk.plugin import BmtPlugin


def exec_plugin_module(project_dir: Path) -> ModuleType:
    """Import ``<project_dir>/plugin.py`` with sibling modules on ``sys.path``."""

    plugin_py = project_dir / "plugin.py"
    if not plugin_py.is_file():
        raise FileNotFoundError(f"Expected plugin.py at {plugin_py}")

    module_name = f"bmt_plugin_{project_dir.name}_{id(project_dir)}"
    spec = importlib.util.spec_from_file_location(module_name, plugin_py)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not create module spec for {plugin_py}")

    path_str = str(project_dir)
    added = path_str not in sys.path
    if added:
        sys.path.insert(0, path_str)
    try:
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if added and path_str in sys.path:
            sys.path.remove(path_str)


def load_plugin_direct(project_dir: Path) -> tuple[BmtPlugin, Path]:
    """Load a plugin from ``<project_dir>/plugin.py`` by module shape.

    Project modules export ``plugin()`` returning a :class:`BmtPlugin`.
    """
    module = exec_plugin_module(project_dir)
    return load_plugin_from_module(module), project_dir


def load_plugin(
    stage_root: Path,
    project: str,
    plugin_ref: str = "direct",  # noqa: ARG001 - compatibility; direct loader ignores refs
    *,
    allow_workspace: bool = True,  # noqa: ARG001 - compatibility; direct loader ignores workspace policy
) -> tuple[BmtPlugin, Path]:
    """Load a BmtPlugin from ``stage_root/projects/<project>/plugin.py``.

    ``plugin_ref`` and ``allow_workspace`` are accepted for API compatibility with
    published-plugin planning, but this loader resolves the staged project directly.
    """
    project_dir = stage_root / "projects" / project
    return load_plugin_direct(project_dir)
