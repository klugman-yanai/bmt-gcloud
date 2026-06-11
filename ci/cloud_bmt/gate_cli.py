"""CLI for gate bucket preflight (``bmt gate verify``)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from cloud_bmt import config
from cloud_bmt.gate_verify import run_verify

app = typer.Typer(
    no_args_is_help=True,
    help="Gate bucket preflight before Cloud BMT dispatch.",
)


@app.command("verify")
def verify(
    projects: Annotated[
        str | None,
        typer.Option(
            "--projects",
            "-p",
            help="Comma-separated project slugs or JSON array (defaults to ACCEPTED_PROJECTS / checkout discovery).",
        ),
    ] = None,
    bucket: Annotated[
        str | None,
        typer.Option("--bucket", "-b", help="GCS bucket (defaults to $GCS_BUCKET)."),
    ] = None,
    stage_root: Annotated[
        str | None,
        typer.Option(
            "--stage-root",
            help="Stage root for manifest discovery (defaults to $BMT_STAGE_ROOT or generated/stage).",
        ),
    ] = None,
    *,
    skip_prepared_cache: Annotated[
        bool,
        typer.Option("--skip-prepared-cache", help="Do not scan SK _prepared/ for gcsfuse corruption."),
    ] = False,
) -> None:
    """Verify datasets, runners, and plugin metadata on the gate bucket."""
    if bucket:
        os.environ["GCS_BUCKET"] = bucket
    cfg = config.get_config()
    root = Path(stage_root).resolve() if stage_root else None
    run_verify(
        cfg,
        projects_csv=projects,
        stage_root=root,
        check_prepared_cache=not skip_prepared_cache,
    )
