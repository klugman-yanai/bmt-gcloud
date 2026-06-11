"""Tag map + semver helpers (runtime copy; mirrors ci/config/tag_to_gate.json)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from semver import Version

_TAG_CONFIG = Path(__file__).resolve().parents[1] / "config" / "tag_to_gate.json"
_RELEASE_SUFFIX = re.compile(r"^v[0-9]", re.IGNORECASE)


@lru_cache(maxsize=1)
def _prefix_for_gate_project() -> dict[str, str]:
    raw = json.loads(_TAG_CONFIG.read_text(encoding="utf-8"))
    rows = raw.get("entries", []) if isinstance(raw, dict) else []
    out: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        prefix = str(row.get("tag_prefix", "")).strip().lower()
        gate = str(row.get("gate_project", "")).strip().lower()
        if prefix and gate:
            out[gate] = prefix
    return out


def tag_prefix_for_gate_project(gate_project: str) -> str | None:
    return _prefix_for_gate_project().get(gate_project.strip().lower())


def parse_release_tag(tag: str) -> tuple[str, str] | None:
    text = tag.strip()
    if "/" not in text:
        return None
    prefix_raw, suffix = text.split("/", 1)
    prefix = prefix_raw.strip().lower()
    version = suffix.strip()
    if not prefix or not version or not _RELEASE_SUFFIX.match(version):
        return None
    if prefix not in set(_prefix_for_gate_project().values()):
        return None
    return prefix, version


def _version_sort_key(version_suffix: str) -> tuple[int, ...] | None:
    text = version_suffix.strip()
    if text.lower().startswith("v"):
        text = text[1:]
    parts: list[int] = []
    for piece in text.split("."):
        if not piece.isdigit():
            return None
        parts.append(int(piece))
    return tuple(parts) if parts else None


def tag_version_key(version_suffix: str) -> Version | None:
    text = version_suffix.strip()
    if text.lower().startswith("v"):
        text = text[1:]
    pieces = text.split(".")
    if len(pieces) > 3:
        text = ".".join(pieces[:3])
    try:
        return Version.parse(text, optional_minor_and_patch=True)
    except ValueError:
        return None


def newest_release_tag_for_prefix(tags: list[str], tag_prefix: str) -> str | None:
    want = tag_prefix.strip().lower()
    best_ver: tuple[int, ...] | None = None
    best_tag: str | None = None
    for tag in tags:
        parsed = parse_release_tag(tag)
        if parsed is None or parsed[0] != want:
            continue
        key = _version_sort_key(parsed[1])
        if key is None:
            continue
        if best_ver is None or key > best_ver:
            best_ver = key
            best_tag = tag.strip()
    return best_tag
