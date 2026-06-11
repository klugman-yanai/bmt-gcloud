# cloud-ci-handoff — agent context

Generic **GitHub Actions → Workflows → Cloud Run** handoff template. Python 3.12+, `uv`, `just`.

`AGENTS.md` is the compact contract for coding agents. User-facing setup and rationale live in `README.md`.

## Commands

```bash
uv sync
just test          # pytest suite
just typecheck     # ty check (sections via justfile)
ruff check .       # lint
uv run python -m tools --help
```

## Architecture

```
GitHub Actions → Google Workflows → Cloud Run (plan / task / coordinator) → GCS → GitHub API
```

| Layer | Path | Owns |
| --- | --- | --- |
| CI driver | `ci/cloud_bmt/` | Matrix discovery, handoff, gate verification |
| Runtime | `runtime/` | Plan legs, execute plugins, update pointers |
| SDK | `sdk/bmt_sdk/` | Plugin protocol and scoring helpers |
| Projects | `projects/<slug>/` | `plugin.py` + `project.bmt.json` |
| Tools | `tools/` | Bucket sync, monitor, layout validators |

## Plugin contract

Plugins implement `BmtPlugin` via `custom_plugin(...)` hooks:

1. `prepare` — light setup
2. `execute` — run workload, emit `CaseResult` rows
3. `score` — aggregate metrics
4. `evaluate` — pass/fail verdict with stable `reason_code`

Start from [`examples/custom_plugin.py`](examples/custom_plugin.py) or [`projects/demo/plugin.py`](projects/demo/plugin.py).

## Boundaries

- Do not reintroduce customer-specific OEM names, audio scoring, or proprietary runner binaries.
- Terraform/Pulumi values in `infra/` are templates — never commit real secrets or production bucket names.
- `generated/` and `data/` are local artifacts; do not commit.

## Documentation ownership

- Update `README.md` for user-facing behavior changes.
- Update `AGENTS.md` for agent workflow, layout, or contract changes.
- Update `docs/architecture.md` when the runtime storage model or handoff flow changes.
