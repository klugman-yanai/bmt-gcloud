"""BMT project scaffolding and publishing."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(no_args_is_help=True)


@app.command("add-project")
def add_project(
    project: Annotated[
        str,
        typer.Argument(help="Project name (lowercase, e.g. myproject)"),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate the request without writing files"),
    ] = False,
) -> None:
    """Copy the suite examples/ scaffold to projects/<project>/ at the suite root."""
    from tools.bmt.scaffold import add_project as add_project_impl

    raise typer.Exit(add_project_impl(project, dry_run=dry_run))


@app.command("add-bmt")
def add_bmt(
    project: Annotated[
        str,
        typer.Argument(help="Project name (lowercase, e.g. myproject)"),
    ],
    bmt_slug: Annotated[
        str,
        typer.Argument(help="BMT slug (lowercase, e.g. false_rejects)"),
    ],
) -> None:
    """Add a disabled flat BMT manifest under projects/<project>/."""
    from tools.bmt.scaffold import add_bmt as add_bmt_impl

    raise typer.Exit(add_bmt_impl(project, bmt_slug))


@app.command("add-plugin-package")
def add_plugin_package(
    project: Annotated[
        str,
        typer.Argument(help="Project name (lowercase, e.g. myproject)"),
    ],
    plugin_slug: Annotated[
        str,
        typer.Argument(help="Plugin slug (lowercase, e.g. keyword)"),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate the request without writing files"),
    ] = False,
) -> None:
    """Add a worker plugin package and register it in plugins/registry.yaml."""
    from tools.bmt.plugin_package_scaffold import add_plugin_package as add_plugin_package_impl

    raise typer.Exit(add_plugin_package_impl(project, plugin_slug, dry_run=dry_run))


@app.command("validate-plugin-registry")
def validate_plugin_registry(
    project: Annotated[
        str,
        typer.Argument(help="Project name (lowercase, e.g. myproject)"),
    ],
) -> None:
    """Validate plugin registry descriptors for a project."""
    from tools.bmt.plugin_registry_validate import validate_plugin_registry as validate_plugin_registry_impl

    raise typer.Exit(validate_plugin_registry_impl(project))


@app.command("publish-bmt")
def publish_bmt(
    project: Annotated[
        str,
        typer.Argument(help="Project name"),
    ],
    bmt_slug: Annotated[
        str,
        typer.Argument(help="BMT slug"),
    ],
    no_sync: Annotated[
        bool,
        typer.Option("--no-sync", help="Only publish locally; skip syncing the project subtree to GCS"),
    ] = False,
) -> None:
    """Validate locally, publish an immutable plugin bundle, and sync to GCS."""
    from tools.bmt.publisher import publish_bmt as publish_bmt_impl

    result = publish_bmt_impl(project=project, bmt_slug=bmt_slug, sync=not no_sync)
    typer.echo(f"{result.project}: plugin.py sha256-{result.digest}")
    raise typer.Exit(0)


@app.command("symlink-deps")
def symlink_deps(
    bmt_root: Annotated[
        Path | None,
        typer.Option("--bmt-root", help="BMT root dir; default from BMT_ROOT env or repo default"),
    ] = None,
    deps_dir: Annotated[
        Path | None,
        typer.Option("--deps-dir", help="Override shared deps directory"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print what would be done"),
    ] = False,
) -> None:
    """Symlink shared BMT native deps into each project's runner lib directory."""
    from tools.scripts.symlink_bmt_deps import run as symlink_deps_run

    rc = symlink_deps_run(bmt_root=bmt_root, deps_dir=deps_dir, dry_run=dry_run)
    raise typer.Exit(rc)


@app.command("materialize-projects")
def materialize_projects(
    clean: Annotated[
        bool,
        typer.Option("--clean/--no-clean", help="Clean generated stage projects before copying root projects"),
    ] = True,
) -> None:
    """Materialize projects/<slug>/ sources into generated/stage."""
    from tools.bmt.materialize import materialize_projects as materialize_projects_impl

    projects = materialize_projects_impl(clean=clean)
    for project in projects:
        typer.echo(f"{project.source_dir.name} -> {project.target_dir}")
    raise typer.Exit(0)
