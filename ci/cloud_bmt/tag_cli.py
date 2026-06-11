"""CLI for OEM git tag → gate project resolution."""

from __future__ import annotations

import os
from typing import Annotated

import typer

from cloud_bmt import core
from cloud_bmt.actions import gh_notice
from cloud_bmt.tag_gate import resolve_tag, write_github_outputs

tag_app = typer.Typer(help="OEM release tag mapping for core-main tag CI.")


@tag_app.command("resolve")
def tag_resolve(
    tag: Annotated[str, typer.Option("--tag", help="Full git tag (e.g. SK/v1.2.3).")],
) -> None:
    """Write tag→gate mapping to GITHUB_OUTPUT (skip=true when unmapped)."""
    gh_out = core.require_env("GITHUB_OUTPUT")
    result = resolve_tag(tag)
    write_github_outputs(result, github_output=gh_out)
    if result is None:
        gh_notice(f"Tag {tag!r} is not a mapped OEM release tag; skipping runner publish.")
        return
    gh_notice(f"Tag {result.tag} → gate project {result.entry.gate_project} (preset {result.entry.build_preset}).")


@tag_app.command("show")
def tag_show(
    tag: Annotated[str, typer.Argument(help="Full git tag to resolve.")],
) -> None:
    """Print resolved mapping to stdout (local debugging)."""
    result = resolve_tag(tag)
    if result is None:
        typer.echo(f"unmapped: {tag}")
        raise typer.Exit(1)
    e = result.entry
    typer.echo(f"gate_project={e.gate_project}")
    typer.echo(f"configure_preset={e.configure_preset}")
    typer.echo(f"build_preset={e.build_preset}")
    typer.echo(f"bmt_key={e.bmt_key}")


def main_tag_resolve_from_env() -> None:
    tag = (os.environ.get("GIT_TAG") or os.environ.get("GITHUB_REF_NAME") or "").strip()
    if not tag:
        raise RuntimeError("GIT_TAG or GITHUB_REF_NAME is required")
    tag_resolve(tag=tag)
