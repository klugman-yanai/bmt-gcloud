"""GCS bucket operations."""

from __future__ import annotations

import io
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Annotated

import typer

from tools.repo.paths import DEFAULT_STAGE_ROOT, repo_root, suite_root
from tools.shared.bucket_env import bucket_from_env
from tools.shared.rich_minimal import step, step_console, success_panel

app = typer.Typer(no_args_is_help=True)


@app.command("verify-runtime-seed")
def verify_runtime_seed() -> None:
    """Verify runtime seed sync (manifest vs bucket)."""
    from tools.remote.bucket_verify_runtime_seed_sync import BucketVerifyRuntimeSeedSync

    bucket = bucket_from_env()
    rc = BucketVerifyRuntimeSeedSync().run(bucket=bucket)
    raise typer.Exit(rc)


@app.command()
def deploy() -> None:
    """Materialize root Cloud BMT projects, sync stage to bucket, and verify.

    On success, emits ``plugins_sha`` (the git tree SHA of root Cloud BMT projects
    at HEAD) to ``$GITHUB_OUTPUT`` so the CI release workflow can record which
    plugin state was deployed. Local runs print it for visibility only.
    """
    from tools.bmt.materialize import materialize_projects
    from tools.remote.bucket_sync_runtime_seed import BucketSyncRuntimeSeed
    from tools.remote.bucket_verify_runtime_seed_sync import BucketVerifyRuntimeSeedSync
    from tools.shared.release_fingerprints import emit_github_output, plugins_tree_sha

    bucket = bucket_from_env()
    console = step_console()
    if console is not None:
        console.print("[bold]Deploy[/]")
    materialize_projects()
    steps: list[tuple[str, BucketSyncRuntimeSeed | BucketVerifyRuntimeSeedSync]] = [
        ("Sync runtime seed", BucketSyncRuntimeSeed()),
        ("Verify runtime seed", BucketVerifyRuntimeSeedSync()),
    ]
    for label, runner in steps:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = runner.run(bucket=bucket)
        if rc != 0:
            if buf.getvalue():
                sys.stderr.write(buf.getvalue())
            step(console, label, ok=False)
            raise typer.Exit(rc)
        step(console, label, ok=True)

    plugins_sha = plugins_tree_sha(Path(suite_root()))
    if plugins_sha is not None:
        print(f"PLUGINS_SHA={plugins_sha}")
        emit_github_output("plugins_sha", plugins_sha)
    success_panel(console, "Deploy", "Runtime seed synced and verified.")
    raise typer.Exit(0)


@app.command()
def preflight(
    snapshot: Annotated[
        Path | None,
        typer.Option(
            "--snapshot",
            "--report",
            help="Replay diff from a saved JSON snapshot (--report is an alias).",
        ),
    ] = None,
    local_only: Annotated[
        bool,
        typer.Option("--local-only", help="Only list gcp/image, no GCS"),
    ] = False,
) -> None:
    """Bucket diff vs gcp/image (JSON snapshot under .local/ on live runs)."""
    from tools.remote.preflight_bucket import run_preflight

    console = step_console()
    if console is not None and snapshot is None and not local_only:
        console.print("[bold]Preflight[/]")
    rc = run_preflight(snapshot=snapshot, local_only=local_only)
    step(console, "Preflight", ok=(rc == 0))
    if rc == 0:
        success_panel(console, "Preflight", "Bucket preflight passed.")
    raise typer.Exit(rc)


@app.command("clean-bloat")
def clean_bloat(
    execute: Annotated[
        bool,
        typer.Option("--execute", help="Actually delete (default is dry-run)"),
    ] = False,
) -> None:
    """Remove Python/uv bloat from GCS bucket."""
    from tools.remote.bucket_clean_bloat import BucketCleanBloat

    bucket = bucket_from_env()
    console = step_console()
    if console is not None:
        console.print("[bold]Clean bloat[/]")
    rc = BucketCleanBloat().run(bucket=bucket, dry_run=not execute)
    step(console, "Clean bloat", ok=(rc == 0))
    if rc == 0:
        success_panel(console, "Clean bloat", "Done (see above for details).", style="blue")
    raise typer.Exit(rc)


@app.command("upload-runner")
def upload_runner(
    runner_path: Annotated[
        Path | None,
        typer.Option(
            "--runner-path",
            envvar="BMT_RUNNER_PATH",
            help="Path to runner binary; default from BMT_RUNNER_PATH or sk default",
        ),
    ] = None,
    runner_uri: Annotated[
        str | None,
        typer.Option(
            "--runner-uri",
            envvar="BMT_RUNNER_URI",
            help="GCS object path; default from BMT_RUNNER_URI or sk default",
        ),
    ] = None,
    source: Annotated[
        str | None,
        typer.Option(
            "--source",
            envvar="BMT_SOURCE",
            help="Source label for metadata (default sandbox_manual)",
        ),
    ] = None,
    source_ref: Annotated[
        str | None,
        typer.Option(
            "--source-ref",
            envvar="SOURCE_REF",
            help="Optional source ref (commit, etc.)",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Upload even if size matches existing"),
    ] = False,
) -> None:
    """Upload runner binary with previous-version rotation and metadata."""
    import os

    from tools.remote.bucket_upload_runner import BucketUploadRunner

    bucket = bucket_from_env()
    path = runner_path or (
        (os.environ.get("BMT_RUNNER_PATH") or "").strip() or "repo/staging/runners/sk_gcc_release/cloud_bench_runner"
    )
    uri = runner_uri or ((os.environ.get("BMT_RUNNER_URI") or "").strip() or "sk/runners/sk_gcc_release/cloud_bench_runner")
    source_eff = (source or (os.environ.get("BMT_SOURCE") or "").strip() or "sandbox_manual").strip()
    source_ref_eff = (source_ref or (os.environ.get("SOURCE_REF") or "").strip()).strip()
    rc = BucketUploadRunner().run(
        bucket=bucket,
        runner_path=path,
        runner_uri=uri,
        source=source_eff,
        source_ref=source_ref_eff,
        force=force,
    )
    raise typer.Exit(rc)


@app.command("bootstrap-runner-meta")
def bootstrap_runner_meta(
    project: Annotated[
        str,
        typer.Option("--project", help="Project slug, e.g. skyworth"),
    ],
    preset: Annotated[
        str,
        typer.Option("--preset", help="Release preset, e.g. SKYWORTH_gcc_Release-build"),
    ],
    source_ref: Annotated[
        str,
        typer.Option("--source-ref", help="Core-main commit SHA used to build the binaries"),
    ],
    binaries: Annotated[
        Path,
        typer.Option(
            "--binaries", exists=True, file_okay=False, help="Directory with cloud_bench_runner and libCloud Bench.so"
        ),
    ],
) -> None:
    """Upload runner binaries and flat metadata for a preseeded project."""
    from tools.remote.bucket_bootstrap_runner_meta import BucketBootstrapRunnerMeta

    bucket = bucket_from_env()
    rc = BucketBootstrapRunnerMeta().run(
        bucket=bucket,
        project=project,
        preset=preset,
        source_ref=source_ref,
        binaries=binaries,
    )
    raise typer.Exit(rc)


@app.command("upload-dataset")
def upload_dataset(
    project: Annotated[
        str,
        typer.Argument(help="Project name (e.g. sk)"),
    ],
    dataset: Annotated[
        str,
        typer.Argument(help="Dataset name (e.g. false_alarms)"),
    ],
    source: Annotated[
        str,
        typer.Argument(help="Local file path, local folder path, or Google Drive folder ID (with --drive)"),
    ],
    drive: Annotated[
        bool,
        typer.Option("--drive", help="Source is a Google Drive folder ID; transfer runs via Cloud Run (non-blocking)"),
    ] = False,
    recursive: Annotated[
        bool,
        typer.Option("--recursive", "-r", help="Source is a local folder; use gcloud storage rsync"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Re-upload even if GCS already matches (local modes only)"),
    ] = False,
    local: Annotated[
        bool,
        typer.Option(
            "--local",
            help="Also mirror files into generated/stage/ (off by default; datasets can be 30-40 GB)",
        ),
    ] = False,
) -> None:
    """Upload a WAV dataset to projects/<project>/inputs/<dataset>/.

    Three modes:

    \b
    Single file (up to 20 GB):
        uv run bmt bucket upload-dataset sk my_data /path/to/audio.wav

    Local folder (recursive):
        uv run bmt bucket upload-dataset sk my_data /path/to/folder --recursive

    Google Drive folder (non-blocking Cloud Run job):
        uv run bmt bucket upload-dataset sk my_data <drive-folder-id> --drive
    """
    from tools.remote.bucket_upload_dataset import BucketUploadDataset
    from tools.repo.paths import repo_root

    bucket = bucket_from_env()
    local_mirror = repo_root() / DEFAULT_STAGE_ROOT if local else None

    if drive:
        rc = BucketUploadDataset().run(
            bucket=bucket,
            project=project,
            source="",
            dataset_name=dataset,
            drive=True,
            drive_folder_id=source,
        )
    else:
        rc = BucketUploadDataset().run(
            bucket=bucket,
            project=project,
            source=Path(source),
            dataset_name=dataset,
            force=force,
            local_mirror=local_mirror,
        )
    raise typer.Exit(rc)


@app.command("promote-dataset")
def promote_dataset(
    project: Annotated[str, typer.Argument(help="Gate project slug (e.g. sdmc)")],
    dataset: Annotated[str, typer.Argument(help="Dataset slug (e.g. false_rejects)")],
    source_prefix: Annotated[
        str,
        typer.Option(
            "--source-prefix",
            help="Prefix inside source bucket (e.g. 01_Projects/SDMC/raw_audio/FRR)",
        ),
    ] = "",
    profile: Annotated[
        str,
        typer.Option("--profile", help="Named profile from ci/config/dataset_promotion_profiles.json"),
    ] = "",
    source_bucket: Annotated[
        str,
        typer.Option("--source-bucket", help="Source GCS bucket (default: krdm_bmt_per_project)"),
    ] = "",
    dest_bucket: Annotated[
        str,
        typer.Option("--dest-bucket", help="Destination gate bucket (default: GCS_BUCKET)"),
    ] = "",
    kind: Annotated[
        str,
        typer.Option("--kind", help="Stage segment: inputs, audio, or assets"),
    ] = "inputs",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print rsync actions without copying")] = False,
    no_clobber: Annotated[
        bool,
        typer.Option("--no-clobber/--clobber", help="Skip objects that already exist at destination"),
    ] = True,
    smoke_prefix: Annotated[
        str,
        typer.Option("--smoke-prefix", help="Copy only this session/subfolder under the source prefix"),
    ] = "",
    skip_manifest: Annotated[
        bool,
        typer.Option("--skip-manifest", help="Do not regenerate dataset_manifest.json"),
    ] = False,
) -> None:
    """Promote a dataset from one GCS bucket/prefix into the gate bucket (server-side rsync)."""
    from tools.remote.bucket_promote_dataset import DEFAULT_SOURCE_BUCKET, BucketPromoteDataset

    runner = BucketPromoteDataset()
    if profile:
        rc = runner.run_profile(
            profile,
            source_bucket=source_bucket or DEFAULT_SOURCE_BUCKET,
            dest_bucket=dest_bucket or None,
            dry_run=dry_run,
            no_clobber=no_clobber,
            smoke_prefix=smoke_prefix,
            gen_manifest=not skip_manifest,
        )
        raise typer.Exit(rc)

    if not source_prefix.strip():
        print("::error::Pass --source-prefix or --profile", file=sys.stderr)
        raise typer.Exit(1)

    rc = runner.run(
        project=project,
        dataset=dataset,
        source_bucket=source_bucket or DEFAULT_SOURCE_BUCKET,
        source_prefix=source_prefix,
        dest_bucket=dest_bucket or None,
        kind=kind,
        dry_run=dry_run,
        no_clobber=no_clobber,
        smoke_prefix=smoke_prefix,
        gen_manifest=not skip_manifest,
        skip_manifest=skip_manifest,
    )
    raise typer.Exit(rc)


@app.command("promote-oem")
def promote_oem(
    project: Annotated[str, typer.Argument(help="Gate project slug (e.g. freebox, sdmc, sedona)")],
    source_bucket: Annotated[str, typer.Option("--source-bucket", help="Source GCS bucket")] = "",
    dest_bucket: Annotated[str, typer.Option("--dest-bucket", help="Destination gate bucket")] = "",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    no_clobber: Annotated[bool, typer.Option("--no-clobber/--clobber")] = True,
    smoke_prefix: Annotated[str, typer.Option("--smoke-prefix", help="Limit each leg to one session")] = "",
) -> None:
    """Promote all configured legs for an OEM (see dataset_promotion_profiles.json oem_all_legs)."""
    from tools.remote.bucket_promote_dataset import DEFAULT_SOURCE_BUCKET, BucketPromoteDataset

    rc = BucketPromoteDataset().run_oem(
        project,
        source_bucket=source_bucket or DEFAULT_SOURCE_BUCKET,
        dest_bucket=dest_bucket or None,
        dry_run=dry_run,
        no_clobber=no_clobber,
        smoke_prefix=smoke_prefix,
    )
    raise typer.Exit(rc)


@app.command("project-sync")
def project_sync(
    project: Annotated[
        str,
        typer.Argument(help="Project name (e.g. sk)"),
    ],
) -> None:
    """Sync a single staged project subtree to the bucket."""
    from tools.remote.bucket_sync_project import BucketSyncProject

    bucket = bucket_from_env()
    rc = BucketSyncProject().run(bucket=bucket, project=project)
    raise typer.Exit(rc)


@app.command("mount-project")
def mount_project(
    project: Annotated[
        str,
        typer.Argument(help="Project name (e.g. sk)"),
    ],
) -> None:
    """Mount a live project subtree read-only under gcp/mnt/projects/<project>/."""
    mnt_root = repo_root() / "gcp" / "mnt" / "projects" / project
    mnt_root.mkdir(parents=True, exist_ok=True)
    bucket = bucket_from_env()
    rc = subprocess.run(
        [
            "gcsfuse",
            f"--only-dir=projects/{project}",
            "--file-mode=444",
            "--dir-mode=555",
            "--implicit-dirs",
            "--stat-cache-ttl=300s",
            "--type-cache-ttl=300s",
            "--kernel-list-cache-ttl-secs=60",
            bucket,
            str(mnt_root),
        ],
        check=False,
    ).returncode
    raise typer.Exit(rc)


@app.command("umount-project")
def umount_project(
    project: Annotated[
        str,
        typer.Argument(help="Project name (e.g. sk)"),
    ],
) -> None:
    """Unmount a project gcsfuse mount under gcp/mnt/projects/<project>/."""
    mnt_root = repo_root() / "gcp" / "mnt" / "projects" / project
    rc = subprocess.run(
        ["fusermount", "-u", str(mnt_root)],
        check=False,
    ).returncode
    raise typer.Exit(rc)
