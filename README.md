# cloud-ci-handoff

Open-source template for **GitHub Actions → Google Workflows → Cloud Run** batch validation.

CI writes a run trigger, dispatches cloud jobs, and exits. Cloud Run executes plugin-defined workloads, writes results to object storage, and posts pass/fail back to GitHub. Branch protection gates merges on the check outcome.

This repository is a **sanitized, generic extract** of a production pipeline pattern. Proprietary OEM workloads, scoring logic, and customer data were removed. What remains is the reusable infrastructure: handoff orchestration, plugin SDK, runtime planner/coordinator, devtools, and a `demo` project you can copy.

## Why this exists

Use it as a starting point when you want:

- PR-gated cloud jobs without blocking Actions on long-running work
- A plugin contract (`prepare` → `execute` → `score` → `evaluate`)
- Pointer-based results (`current.json` + per-run snapshots)
- Repo-local agent guidance (`AGENTS.md`) for Cursor/Claude-style development

## Quick start

```bash
uv sync
just --list
just test
```

Copy [`examples/plugin.py`](examples/plugin.py) into [`projects/demo/`](projects/demo/) (or a new `projects/<slug>/` folder) and edit the hooks.

## Layout

| Path | Role |
| --- | --- |
| `ci/` | Handoff CLI and GitHub workflow drivers |
| `runtime/` | Cloud Run planner, task worker, coordinator |
| `sdk/` | Plugin author SDK (`bmt_sdk`) |
| `projects/demo/` | Minimal example project |
| `examples/` | Scaffold to copy for new projects |
| `infra/` | Pulumi/Terraform templates (fill in your GCP project) |
| `tools/` | Bucket sync, monitor, local validation helpers |
| `tests/` | CI/runtime/repo contract tests |

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the production flow, storage contract, and coordinator behavior.

## Agent-assisted development

[`AGENTS.md`](AGENTS.md) documents commands, boundaries, and the plugin contract for coding agents. [`CLAUDE.md`](CLAUDE.md) points maintainers at the same source of truth.

## License

MIT — see [LICENSE](LICENSE).
