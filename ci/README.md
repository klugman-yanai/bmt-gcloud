# `cloud-bmt` (CI / handoff CLI)

This directory is the **`cloud-bmt`** workspace member ([`pyproject.toml`](pyproject.toml)).

- **Console:** `uv run cloud-bmt …` from the repo root (after `uv sync`). A legacy alias **`bmt`** points at the same entrypoint.
- **Import package:** `cloud_bmt` — e.g. [`cloud_bmt/handoff.py`](cloud_bmt/handoff.py).

Production GitHub workflows typically use the release **`bmt.pex`** via [`.github/actions/setup-bmt-pex`](../.github/actions/setup-bmt-pex/action.yml) instead of vendoring this tree.

## Matrix snapshot commands

- **`matrix extract-core-main-presets`** — emits `presets_release` / `presets_nonrelease` from `CMakePresets.json`; host linux Release presets publish runner artifacts, while BMT support is determined later by the suite's Cloud BMT projects/runtime.
- **`matrix ci-snapshot-suite`** — emits `release_presets` / `non_release_presets` (parity with this repo **`build-and-test.yml`** `repo_snapshot`, formerly `jq`). **`matrix ci-snapshot-bmt-gcloud`** remains as a deprecated alias for one release.
- **`runner filter-bmt-presets`** — scans `upstream-artifacts/*/metadata.json` (override with `FILTER_BMT_ARTIFACT_ROOT`); writes `matrix`, `count`, `has_presets`.
- **`runner bundle-core-main-artifact`** — stages `runner/*` + root `metadata.json` under `ARTIFACT_ROOT` for Cloud Bench-org/core-main `upload-artifact` (env: `CONFIGURE_PRESET`, `BUILD_PRESET`, `BMT_KEY`, `ARCH`, `OS_NAME`, `RUNNABLE_ON_BMT_RUNNER`; optional `BMT_REPO_ROOT`, `BMT_PRESETS_FILE`). Copies `Cloud Bench/*.so*` when present (LGTV preprocessor libs).
- **`runner normalize-handoff-artifact`** — after downloading `runner-*` in handoff; layout from `projects/<slug>/project.bmt.json` (`flat_binary` vs `bundle_directory`).

Use env `BMT_REPO_ROOT` when the presets file paths are relative (default `.`). Outputs require `GITHUB_OUTPUT` except when piping locally.

## Consumer repos (e.g. core-main)

Cross-repo callers depend on **`cloud-bmt-suite`** as a **git** or **index** source (see root [`pyproject.toml`](../pyproject.toml) `[tool.uv.sources]`). They do **not** install from `.github/bmt`; pin **`rev`** to a tag or full SHA when using git sources.

After configuring sources, run **`uv lock`** / **`uv sync`**, then **`uv run cloud-bmt …`** (or invoke the PEX in CI). Prefer pinning **`uses: Cloud Bench-org/cloud-bmt-suite/.../@bmt-v*`** once the snapshot commands you need ship in **`bmt.pex`** built from that tag.
