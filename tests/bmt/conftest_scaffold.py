"""Shared helpers for scaffold tests."""

from __future__ import annotations

import shutil
from pathlib import Path

from tools.repo.paths import suite_root


def seed_examples_template(source_root: Path) -> Path:
    """Copy the suite ``examples/`` tree into ``source_root`` for scaffold tests."""
    template = suite_root() / "examples"
    target = source_root / "examples"
    if not template.is_dir():
        raise FileNotFoundError(f"Suite examples scaffold is missing: {template}")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(template, target)
    return target
