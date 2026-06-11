# Adding A Cloud BMT Project

Cloud BMT project source lives at `projects/<slug>/` at the suite root.
Generated stage output is build output under `cloud-ci-handoff/generated/stage/`.

**Cloud-first:** implement the BMT under `projects/<slug>/` and gate paths; do not change
`bmt-handoff.yml`, Workflows, or Cloud Run orchestration to match legacy VM/unified BMT layouts.
Read **[bmt-adaptation-principles.md](bmt-adaptation-principles.md)** first.

For a clean starting point, copy `examples/` from the suite root. Plugin authoring:
[`docs/plugins.md`](../../docs/plugins.md). Production examples: `projects/sk/`, `projects/skyworth/`.

## Project Source

A project directory should contain:

- `project.bmt.json` — project metadata, runner defaults, and all BMT leg settings
- `plugin.py` — a `plugin()` factory returning a `BmtPlugin`
- `inputs/<leg>/.keep` placeholders only (WAVs live in the gate bucket)

Do not commit runner binaries, native libraries, WAV corpora, or generated
outputs. Local runner/cache files belong under ignored `.local/` paths.

## Start From The Template

From the suite root:

```bash
just add-project myproject
```

Equivalent: `cd cloud-ci-handoff && just add-project myproject` or `uv run python -m tools bmt add-project myproject`.

Or copy `examples/` manually:

```bash
cp -R examples projects/myproject
```

Then edit `projects/myproject/project.bmt.json`, change `"project"` and
`"description"`, and remove `"template": true`. The template is skipped by
materialization until that field is removed.

Do not add a project-local `pyproject.toml` for normal plugins. Cloud BMT runs
inside one shared Python runtime image, so runtime Python packages must be
available in that shared environment. If a project needs an additional package,
declare it in `project.bmt.json`:

```json
"python_dependencies": [
  "example-package>=1.0,<2"
]
```

Then update the shared runtime dependency set in `cloud-ci-handoff/pyproject.toml`
before deploying the project. A project should only have its own `pyproject.toml`
when it is intentionally packaged and tested as a separate Python distribution.

## IDE And SDK Support

Open the suite root in your editor and sync the root environment:

```bash
uv sync
```

Select this interpreter:

```text
.venv/bin/python
```

Imports such as `from bmt_sdk import cloud_bench_runner` should resolve inside
project `plugin.py` files without adding a project-local package.

For command-line checks, stay at the suite root:

```bash
uv run ty check
uv run ruff check projects/myproject/plugin.py
```

The SDK is a typed, dependency-light package. Prefer importing stable helpers
from [`bmt_sdk`](../sdk/README.md) instead of backend runtime internals. For
Cloud Bench runner projects, define `plugin()` and return `cloud_bench_runner(...)`; the
platform owns prepare, execute, score, and evaluate.

Plugin guide: [`docs/plugins.md`](../../docs/plugins.md).

## Materialize Stage

From the suite root:

```bash
just stage-projects
```

This copies root project sources into:

```text
cloud-ci-handoff/generated/stage/projects/<project>/
```

The runtime/GCS contract remains:

```text
stage_root/projects/<project>/...
```

## Add A BMT

Add a new entry under `bmts` in `project.bmt.json`. Standard input, result, and output prefixes are derived from the project and BMT slug unless you override them. Keep project-specific parsing, scoring, and verdict copy in plugin/scoring Python; leave orchestration and reporting to the backend.

To show manual operator notes in the GitHub **BMT Gate** Check output, add
`run_notes` to any BMT entry. It may be a string or a list of
strings. The runtime copies those notes into the leg summary, and the Checks tab
shows them for pending, running, and completed legs.

After editing source:

```bash
just stage-projects
cd cloud-ci-handoff
uv run python -m pytest tests/bmt/test_stage_bmt_manifests.py -q
```

## Promote data from the per-project bucket

To copy corpora from `gs://krdm_bmt_per_project` into the gate bucket (server-side),
see **[dataset-promotion.md](dataset-promotion.md)** and run `just promote-dataset` /
`just promote-oem` from the suite root.

## Upload Data

Datasets live in the bucket under:

```text
projects/<project>/inputs/<dataset>/
```

Use the backend upload helper from `cloud-ci-handoff/`:

```bash
just upload-data <project> /path/to/dataset.zip
```

Pass `--local` only when you intentionally want a local mirror under
`cloud-ci-handoff/generated/stage/` for smoke testing.

## Publish And Deploy

`just deploy` from `cloud-ci-handoff/` materializes root project sources and syncs the
generated runtime seed to the bucket. CI reads the bucket, so local source edits
are not enough for a real cloud run.

## LGTV (custom plugin, same runtime)

LGTV is a normal OEM plugin (`projects/lgtv/plugin.py`, `plugin()` + custom hooks) with gate-staged `cloud_bench_runner` + `sensory`.
It still runs through the **same** handoff and plan/task/coordinator path — only manifests and
plugin code differ. See **[`docs/lgtv-cloud-integration.md`](../../docs/lgtv-cloud-integration.md)**.

## SK Reference

`projects/sk/` is the worked example:

- `plugin.py` returns `cloud_bench_runner(...)` with explicit mic/ref channel routing.
- `project.bmt.json` contains project metadata, runner defaults, and both BMT entries.

Runner behavior changes belong in the producing runner project, especially
`Cloud Bench-org/core-main`. Cloud BMT owns paths, switches, scoring policy, and the
benchmark harness contract.
