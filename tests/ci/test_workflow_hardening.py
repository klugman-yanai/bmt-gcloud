"""Workflow hardening and simplification guardrails for .github/**."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from runtime.config.constants import (
    DEFAULT_GCP_PROJECT,
    DEFAULT_GCP_SA_EMAIL,
    DEFAULT_GCP_WIF_PROVIDER,
    DEFAULT_GCS_BUCKET,
)
from tools.repo.paths import repo_root, suite_root

# `uses: ./cloud-ci-handoff/.github/actions/my-action` or legacy `./.github/actions/...`
_LOCAL_COMPOSITE_USES = re.compile(
    r"^\s*uses:\s+\./(?:cloud-ci-handoff/)?\.github/actions/([^@\s#]+)",
    re.MULTILINE,
)
# `uses: ../sibling-action` from `.github/actions/<dir>/action.yml` → `.github/actions/sibling-action`
_ACTION_REL_SIBLING_USES = re.compile(
    r"^\s*uses:\s+\.\./([^@\s#]+)",
    re.MULTILINE,
)

pytestmark = pytest.mark.unit


def test_reusable_workflow_calls_do_not_inherit_secrets() -> None:
    build_workflow = (suite_root() / ".github" / "workflows" / "build-and-test.yml").read_text(encoding="utf-8")
    merged_dispatch = (suite_root() / ".github" / "workflows" / "internal" / "dispatch-branch-workflows.yml").read_text(
        encoding="utf-8",
    )

    assert "secrets: inherit" not in build_workflow
    assert "secrets: inherit" not in merged_dispatch


def test_handoff_declares_and_passes_third_party_pat_for_pex_setup() -> None:
    handoff = (suite_root() / ".github" / "workflows" / "bmt-handoff.yml").read_text(encoding="utf-8")
    build = (suite_root() / ".github" / "workflows" / "build-and-test.yml").read_text(encoding="utf-8")
    dev_build = (suite_root() / ".github" / "workflows" / "build-and-test-dev.yml").read_text(encoding="utf-8")

    assert "THIRD_PARTY_PAT:" in handoff
    assert "required: true" in handoff
    assert "BMT_GITHUB_READ_TOKEN:" in handoff
    assert "BMT_REQUIRES_THIRD_PARTY_PAT:" in handoff
    assert "THIRD_PARTY_PAT is required for cross-repo private PEX and CMakePresets reads." in handoff
    assert "pex_token: ${{ env.BMT_GITHUB_READ_TOKEN }}" in handoff
    assert "token: ${{ env.BMT_GITHUB_READ_TOKEN }}" in handoff
    assert "GH_TOKEN: ${{ github.token }}" in handoff
    assert "github-token: ${{ github.token }}" in handoff
    assert "THIRD_PARTY_PAT: ${{ secrets.THIRD_PARTY_PAT }}" in build
    assert "THIRD_PARTY_PAT: ${{ secrets.THIRD_PARTY_PAT }}" in dev_build


def test_handoff_downloads_matched_runner_artifact_name() -> None:
    handoff = (suite_root() / ".github" / "workflows" / "bmt-handoff.yml").read_text(encoding="utf-8")

    assert "name: ${{ matrix.artifact_name }}" in handoff
    assert "runner-${{ matrix.preset }}" not in handoff
    assert "runner normalize-handoff-artifact" in handoff
    assert "mkdir -p artifact/Runners artifact/Cloud Bench" not in handoff


def test_handoff_infra_failures_do_not_fail_workflow() -> None:
    handoff = (suite_root() / ".github" / "workflows" / "bmt-handoff.yml").read_text(encoding="utf-8")
    prepare = (repo_root() / ".github" / "actions" / "bmt-prepare-context" / "action.yml").read_text(
        encoding="utf-8",
    )
    classify = (repo_root() / ".github" / "actions" / "bmt-filter-handoff-matrix" / "action.yml").read_text(
        encoding="utf-8",
    )
    fallback = (repo_root() / ".github" / "actions" / "bmt-failure-fallback" / "action.yml").read_text(
        encoding="utf-8",
    )

    assert 'runner_matrix: ${{ steps.prepare.outputs.runner_matrix || \'{"include":[]}\' }}' in handoff
    assert "id: prepare\n        continue-on-error: true" in handoff
    assert "id: classify\n        continue-on-error: true" in handoff
    assert "id: failure\n        continue-on-error: true" in handoff
    assert "bmt_final_state=infra_skipped" in handoff
    assert "steps.failure.outputs.failure_class == 'runtime'" in handoff
    assert "parse-release-runners failed" in prepare
    assert "No supported uploaded legs to hand off." in classify
    assert 'steps.x.outputs.classify_has_legs }}" != "true"' in fallback


def test_bmt_pex_workflow_auto_publishes_on_pex_related_dev_changes() -> None:
    workflow = (suite_root() / ".github" / "workflows" / "build-cloud-bmt-pex.yml").read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert "branches:" in workflow
    assert "      - dev" in workflow
    assert '"cloud-ci-handoff/ci/**"' in workflow
    assert '"cloud-ci-handoff/runtime/**"' in workflow
    assert '"projects/**/project.bmt.json"' in workflow
    assert "group: bmt-pex-publish-${{ github.ref }}" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "patch=$((patch + 1))" in workflow
    assert "already_published=true" in workflow
    assert '--target "${GITHUB_SHA}"' in workflow
    assert "if: github.event_name != 'pull_request'" in workflow


def test_workflow_permissions_are_minimal_for_current_steps() -> None:
    handoff = (suite_root() / ".github" / "workflows" / "bmt-handoff.yml").read_text(encoding="utf-8")
    merged_dispatch = (suite_root() / ".github" / "workflows" / "internal" / "dispatch-branch-workflows.yml").read_text(
        encoding="utf-8",
    )

    assert "start_bmt_workflow:" in handoff
    assert "statuses: write" in handoff
    assert "      contents: read" in handoff
    assert "      actions: write" not in handoff

    assert "permissions:" in merged_dispatch
    assert "  actions: write" in merged_dispatch
    assert "  id-token: write" not in merged_dispatch
    assert "  statuses: write" not in merged_dispatch
    assert "GH_TOKEN: ${{ github.token }}" in merged_dispatch
    assert 'gh workflow run "$workflow_file"' in merged_dispatch
    assert "internal/bmt-image-build.yml" in merged_dispatch


def test_handoff_uses_direct_workflow_dispatch_not_gcs_eventarc() -> None:
    handoff = (suite_root() / ".github" / "workflows" / "bmt-handoff.yml").read_text(encoding="utf-8")

    assert "invoke-workflow" in handoff
    assert "write-run-trigger" not in handoff
    assert "gcloud workflows executions list" not in handoff
    assert "gcloud storage cat" not in handoff


def test_handoff_does_not_use_ci_side_github_reporting() -> None:
    """CI does not post pending status or Check Runs — Cloud Run runtime handles all reporting.

    GitHub App credentials live in GCP Secrets Manager; they must not be injected as
    GitHub repo secrets into the handoff workflow.
    """
    handoff = (suite_root() / ".github" / "workflows" / "bmt-handoff.yml").read_text(encoding="utf-8")

    assert "bmt-start-runtime-reporting" not in handoff
    assert "secrets.BMT_GITHUB_APP_ID" not in handoff
    assert "secrets.BMT_GITHUB_APP_DEV_ID" not in handoff
    assert not (repo_root() / ".github" / "actions" / "bmt-start-runtime-reporting").exists()


def test_dev_ci_workflow_does_not_publish_placeholder_runner_artifacts() -> None:
    """Self-CI (build-and-test-dev.yml) uses placeholder build legs and must not upload runner artifacts.

    This workflow now handles both push and pull_request events (trigger-ci-pr.yml was
    removed). Real runner artifacts come from core-main's build-and-test.yml.
    """
    dev_ci = (suite_root() / ".github" / "workflows" / "build-and-test-dev.yml").read_text(encoding="utf-8")

    assert "Release build placeholder (cloud-ci-handoff)" in dev_ci
    assert "working-directory: ." in dev_ci
    assert "Check rolling BMT handoff ref" in dev_ci
    assert "needs.repo_snapshot.outputs.bmt_ref_exists == 'true'" in dev_ci
    assert "preset stage-release-runner" not in dev_ci
    assert "preset compute-info" not in dev_ci
    assert "Upload runner artifact for handoff" not in dev_ci
    assert ".github/actions/artifacts/upload-repo" not in dev_ci


def _specs_with_commit_sha_pins(yaml_text: str) -> list[str]:
    """Return ``owner/repo@{40-hex}`` uses for marketplace actions (local ``./`` refs skipped)."""
    bad: list[str] = []
    for line in yaml_text.splitlines():
        stripped = line.split("#", 1)[0].rstrip()
        if "uses:" not in stripped:
            continue
        m = re.match(r"^\s*(?:-\s)?uses:\s+(?P<spec>\S+)", stripped)
        if not m:
            continue
        spec = m.group("spec")
        if spec.startswith("./"):
            continue
        if "@" not in spec:
            continue
        _name, rev = spec.rsplit("@", 1)
        if len(rev) == 40 and all(c in "0123456789abcdef" for c in rev.lower()):
            bad.append(spec)
    return bad


def test_hardened_workflows_external_uses_use_semver_tags_not_sha_pins() -> None:
    """Prefer rolling ``@vN`` tags over immutable commit pins for third-party actions."""
    paths = (
        suite_root() / ".github" / "workflows" / "build-and-test.yml",
        suite_root() / ".github" / "workflows" / "clang-format-auto-fix.yml",
        suite_root() / ".github" / "workflows" / "internal" / "bmt-image-build.yml",
    )
    offenders: list[str] = []
    for path in paths:
        rel = path.relative_to(suite_root())
        text = path.read_text(encoding="utf-8")
        if "actions/checkout@v4" in text:
            offenders.append(f"{rel}: must not use deprecated actions/checkout@v4")
        offenders.extend(f"{rel}: {spec}" for spec in _specs_with_commit_sha_pins(text))
    assert not offenders, "Invalid external action pins:\n" + "\n".join(offenders)

    clang_format = paths[1].read_text(encoding="utf-8")
    image_build = paths[2].read_text(encoding="utf-8")
    assert "uses: actions/checkout@v6" in clang_format
    assert "uses: actions/checkout@v6" in image_build
    assert "hashicorp/setup-packer@v3" in image_build


def test_unused_bmt_runner_env_action_is_removed() -> None:
    assert not (repo_root() / ".github" / "actions" / "bmt-runner-env").exists()


def test_handoff_declares_opt_in_release_marker_verification() -> None:
    """Phase B.3 of the CI-driven release plan: Plan job must verify the release
    marker before dispatching cloud work, but only when the caller opts in via
    the ``release_git_sha`` input.

    Guards against three regressions at once:

    1. The input is declared on BOTH ``workflow_dispatch`` and ``workflow_call``
       (cross-repo callers invoke via ``workflow_call``; same-repo debug via
       ``workflow_dispatch``).
    2. The verify step is guarded by ``if: … != ''`` so cross-repo callers that
       don't pass the input keep today's behaviour (they rely on a pinned
       reusable-workflow ``@ref``, not our bucket marker).
    3. The step runs BEFORE ``steps.filter`` — a stale marker must short-circuit
       the matrix build, not race it.
    """
    handoff = (suite_root() / ".github" / "workflows" / "bmt-handoff.yml").read_text(encoding="utf-8")

    assert handoff.count("release_git_sha:") == 2, (
        "expected `release_git_sha:` declared in BOTH workflow_dispatch.inputs and workflow_call.inputs; "
        "found " + str(handoff.count("release_git_sha:"))
    )

    assert "Verify release marker" in handoff
    assert "release verify" in handoff
    assert "(inputs.release_git_sha || github.event.inputs.release_git_sha) != ''" in handoff

    verify_idx = handoff.index("Verify release marker")
    filter_idx = handoff.index("- id: filter")
    assert verify_idx < filter_idx, (
        "Verify step must precede the filter step so stale markers short-circuit the matrix."
    )


def _release_push_block(release: str) -> str:
    match = re.search(r"(?ms)^  push:\n(?P<body>.*?)(?=^  workflow_dispatch:)", release)
    assert match, "release.yml must define an on.push block"
    return match.group("body")


def _release_filter_block(release: str, name: str) -> str:
    pattern = rf"(?ms)^            {re.escape(name)}:\n(?P<body>.*?)(?=^            \w+:|^      - name: Resolve)"
    match = re.search(pattern, release)
    assert match, f"release.yml must define paths-filter block {name!r}"
    return match.group("body")


def test_release_runs_after_dev_merges_and_release_tags() -> None:
    release = (suite_root() / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    push = _release_push_block(release)

    assert re.search(r"^\s+- dev$", push, re.MULTILINE)
    assert re.search(r"^\s+- ci/check-bmt-gate$", push, re.MULTILINE)
    assert re.search(r'^\s+- "bmt-v\*"$', push, re.MULTILINE)


def test_release_path_filters_cover_runtime_sdk_tools_and_all_projects() -> None:
    release = (suite_root() / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    runtime = _release_filter_block(release, "runtime")
    plugins = _release_filter_block(release, "plugins")

    for expected in (
        "cloud-ci-handoff/runtime/**",
        "cloud-ci-handoff/sdk/**",
        "cloud-ci-handoff/pyproject.toml",
        "cloud-ci-handoff/uv.lock",
        "cloud-ci-handoff/ci/pyproject.toml",
    ):
        assert f"- '{expected}'" in runtime

    for expected in (
        "projects/**",
        "cloud-ci-handoff/tools/**",
        "cloud-ci-handoff/generated/stage/**",
    ):
        assert f"- '{expected}'" in plugins

    assert "'projects/sk/**'" not in plugins
    assert "'projects/skyworth/**'" not in plugins


def test_handoff_uses_repo_qualified_composite_actions() -> None:
    """Cross-repo callers must resolve composites from cloud-bmt-suite@tag (literal ``uses:``)."""
    handoff = (suite_root() / ".github" / "workflows" / "bmt-handoff.yml").read_text(encoding="utf-8")
    assert "Cloud Bench-org/cloud-bmt-suite/cloud-ci-handoff/.github/actions/setup-bmt-pex@" in handoff
    assert "uses: ./.github/actions/setup-bmt-pex" not in handoff


def test_handoff_resolves_caller_context_when_inputs_omitted() -> None:
    handoff = (suite_root() / ".github" / "workflows" / "bmt-handoff.yml").read_text(encoding="utf-8")
    assert "BMT_RESOLVED_CI_RUN_ID:" in handoff
    assert "github.run_id" in handoff
    assert "Require ci_run_id for direct workflow_dispatch" in handoff


def test_handoff_declares_force_pass_on_both_triggers() -> None:
    handoff = (suite_root() / ".github" / "workflows" / "bmt-handoff.yml").read_text(encoding="utf-8")
    n = handoff.count("force_pass:")
    assert n == 2, (
        f"expected `force_pass:` declared in BOTH workflow_dispatch.inputs and workflow_call.inputs; found {n}"
    )


def test_handoff_concurrency_keys_repository_and_pr_number() -> None:
    """PR events dedupe by pr_number; non-PR falls back to ref branch+sha."""
    handoff = (suite_root() / ".github" / "workflows" / "bmt-handoff.yml").read_text(encoding="utf-8")
    cidx = handoff.find("\nconcurrency:")
    assert cidx != -1
    block = handoff[cidx : handoff.find("cancel-in-progress:", cidx)]
    assert "github.repository" in block
    assert "inputs.pr_number" in block
    assert "format('pr-{0}'" in block
    assert "format('ref-{0}-{1}'" in block


def test_handoff_resolve_force_pass_reads_pr_labels_and_title() -> None:
    """Dispatch matches core-main: label bmt-gate-override or [bmt-gate-override] in PR title."""
    handoff = (suite_root() / ".github" / "workflows" / "bmt-handoff.yml").read_text(encoding="utf-8")
    start = handoff.find("Resolve force pass")
    assert start != -1
    chunk = handoff[start : start + 2200]
    assert "labels,title" in chunk and "jq -r '.title //" in chunk and "[bmt-gate-override]" in chunk


def test_handoff_declares_bmt_pex_repo_on_both_triggers() -> None:
    handoff = (suite_root() / ".github" / "workflows" / "bmt-handoff.yml").read_text(encoding="utf-8")
    n = handoff.count("bmt_pex_repo:")
    assert n >= 2, (
        "expected `bmt_pex_repo` input in workflow_dispatch and workflow_call (plus optional step `with:`); "
        f"found {n} occurrences"
    )


_EXPECTED_QUARTET: dict[str, str] = {
    "GCS_BUCKET": DEFAULT_GCS_BUCKET,
    "GCP_WIF_PROVIDER": DEFAULT_GCP_WIF_PROVIDER,
    "GCP_SA_EMAIL": DEFAULT_GCP_SA_EMAIL,
    "GCP_PROJECT": DEFAULT_GCP_PROJECT,
}


def _handoff_literal(text: str, name: str) -> str:
    pat = rf"^\s*{re.escape(name)}:\s*\${{{{ vars\.{re.escape(name)} \|\| '([^']*)' }}}}\s*$"
    m = re.search(pat, text, re.MULTILINE)
    assert m, f"expected workflow env fallback for {name}"
    return m.group(1)


def _prepare_context_bash_default(text: str, name: str) -> str:
    pat = rf'^\s*:\s*"\$\{{{re.escape(name)}:=([^}}]+)\}}"\s*$'
    m = re.search(pat, text, re.MULTILINE)
    assert m, f"expected bash default assignment for {name} in bmt-prepare-context"
    return m.group(1)


def test_workflow_gcp_quartet_fallback_literals_match_constants() -> None:
    """Drift guard: ``vars.* || …`` / composite bash defaults must match ``DEFAULT_*``."""
    handoff = (suite_root() / ".github" / "workflows" / "bmt-handoff.yml").read_text(encoding="utf-8")
    release = (suite_root() / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    prepare = (repo_root() / ".github" / "actions" / "bmt-prepare-context" / "action.yml").read_text(encoding="utf-8")

    for name, expected in _EXPECTED_QUARTET.items():
        assert _handoff_literal(handoff, name) == expected, f"bmt-handoff.yml {name}"
        assert _handoff_literal(release, name) == expected, f"release.yml {name}"
        assert _prepare_context_bash_default(prepare, name) == expected, f"bmt-prepare-context {name}"


def test_local_composite_action_paths_resolve() -> None:
    """Every `uses: ./.github/actions/...` reference must have a matching action.yml on disk."""
    github = suite_root() / ".github"
    action_root = repo_root() / ".github" / "actions"
    missing: list[str] = []
    for path in sorted(_github_yaml_files(github) + _github_yaml_files(repo_root() / ".github")):
        text = path.read_text(encoding="utf-8")
        for rel_raw in _LOCAL_COMPOSITE_USES.findall(text):
            rel = rel_raw.strip().rstrip("/")
            action_yml = action_root / rel / "action.yml"
            if not action_yml.is_file():
                missing.append(
                    f"{path.relative_to(suite_root())}: uses …/{rel} -> missing {action_yml.relative_to(suite_root())}"
                )
        if "/actions/" in str(path) and path.name == "action.yml":
            for sibling in _ACTION_REL_SIBLING_USES.findall(text):
                name = sibling.strip().rstrip("/")
                action_yml = action_root / name / "action.yml"
                if not action_yml.is_file():
                    missing.append(
                        f"{path.relative_to(suite_root())}: uses ../{name} -> missing "
                        f"{action_yml.relative_to(suite_root())}"
                    )
    assert not missing, "Broken local action references:\n" + "\n".join(missing)


def _github_yaml_files(github_dir: Path) -> list[Path]:
    out: list[Path] = []
    for pattern in ("*.yml", "*.yaml"):
        out.extend(github_dir.rglob(pattern))
    return out
