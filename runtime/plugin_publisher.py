"""Plugin source hashing for plan legs and publish validation."""

from __future__ import annotations

import hashlib
from pathlib import Path

# Directories that are never plugin source code and must be skipped when
# plugin_root is a full project directory (which may contain large data files).
_DIGEST_SKIP_DIRS: frozenset[str] = frozenset({"__pycache__", "inputs", "plugin_workspaces"})


def plugin_digest(plugin_root: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(
        p
        for p in plugin_root.rglob("*")
        if p.is_file() and not any(part in _DIGEST_SKIP_DIRS for part in p.relative_to(plugin_root).parts)
    ):
        rel = path.relative_to(plugin_root).as_posix().encode("utf-8")
        hasher.update(rel)
        hasher.update(b"\n")
        hasher.update(path.read_bytes())
        hasher.update(b"\n")
    return hasher.hexdigest()
