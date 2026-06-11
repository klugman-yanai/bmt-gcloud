"""Discover and resolve Cloud BMT project source directories at the suite root."""

from __future__ import annotations

from pathlib import Path

from tools.bmt.project_bundle import BUNDLE_MANIFEST_NAME, load_project_bundle
from tools.repo.paths import suite_root

_EXAMPLES_DIRNAME = "examples"
_PROJECTS_DIRNAME = "projects"
_NON_DEPLOYABLE_DIRNAMES = frozenset({_EXAMPLES_DIRNAME})
_FORBIDDEN_LEGACY_SUFFIX = "-cloud-bmt"


def load_project_manifest(source_dir: Path) -> dict[str, object]:
    bundle_path = source_dir / BUNDLE_MANIFEST_NAME
    if not bundle_path.is_file():
        raise FileNotFoundError(f"Cloud BMT project is missing {BUNDLE_MANIFEST_NAME}: {source_dir}")
    return load_project_bundle(bundle_path).project


def project_slug(source_dir: Path) -> str:
    """Return the deployable project slug from the project authoring manifest."""
    project = str(load_project_manifest(source_dir).get("project", "")).strip()
    if not project:
        raise ValueError(f"Cloud BMT project manifest has no project name: {source_dir}")
    return project


def is_template_source(source_dir: Path) -> bool:
    """Return whether a source directory is a non-deployable examples/scaffold tree."""
    if source_dir.name in _NON_DEPLOYABLE_DIRNAMES:
        return True
    return load_project_manifest(source_dir).get("template") is True


def _validate_slug_matches_dir(source_dir: Path) -> None:
    slug = project_slug(source_dir)
    if source_dir.parent.name == _PROJECTS_DIRNAME and source_dir.name != slug:
        raise ValueError(
            f"Project folder name {source_dir.name!r} must match project manifest project={slug!r}: {source_dir}"
        )


def _reject_legacy_layout(base: Path) -> None:
    legacy = sorted(path.name for path in base.glob(f"*{_FORBIDDEN_LEGACY_SUFFIX}") if path.is_dir())
    if legacy:
        joined = ", ".join(legacy)
        raise ValueError(
            f"Legacy *{_FORBIDDEN_LEGACY_SUFFIX} project folders are no longer supported: {joined}. "
            f"Move sources under {_PROJECTS_DIRNAME}/<slug>/ and the scaffold to {_EXAMPLES_DIRNAME}/."
        )


def _projects_layout_sources(base: Path) -> list[Path]:
    projects_root = base / _PROJECTS_DIRNAME
    if not projects_root.is_dir():
        return []
    discovered: list[Path] = []
    for source_dir in sorted(path for path in projects_root.iterdir() if path.is_dir()):
        manifest_path = source_dir / BUNDLE_MANIFEST_NAME
        if not manifest_path.is_file():
            legacy_json = sorted(path.name for path in source_dir.glob("*.json"))
            if legacy_json:
                raise FileNotFoundError(f"Cloud BMT project source must use {BUNDLE_MANIFEST_NAME}: {source_dir}")
            continue
        if is_template_source(source_dir):
            continue
        _validate_slug_matches_dir(source_dir)
        discovered.append(source_dir)
    return discovered


def discover_project_sources(root: Path | None = None) -> list[Path]:
    """Return deployable Cloud BMT project source directories under ``projects/<slug>/``."""
    base = root or suite_root()
    _reject_legacy_layout(base)
    by_slug: dict[str, Path] = {}
    for source_dir in _projects_layout_sources(base):
        slug = project_slug(source_dir)
        if slug in by_slug:
            existing = by_slug[slug]
            raise ValueError(f"Duplicate Cloud BMT project slug {slug!r}: {existing} and {source_dir}")
        by_slug[slug] = source_dir
    return [by_slug[slug] for slug in sorted(by_slug)]


def examples_source_dir(root: Path | None = None) -> Path:
    """Return the suite examples scaffold directory (``examples/``)."""
    base = root or suite_root()
    candidate = base / _EXAMPLES_DIRNAME
    if candidate.is_dir():
        return candidate
    return candidate


def project_source_dir(root: Path | None, project: str) -> Path:
    """Return source dir for ``project`` under the root ``projects/`` layout."""
    base = root or suite_root()
    return base / _PROJECTS_DIRNAME / project
