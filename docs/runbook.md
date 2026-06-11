# Operations runbook

**Audience:** Operators debugging **production** or **staging** BMT runs (GCP, GCS, GitHub). For local development, see [CONTRIBUTING.md](../CONTRIBUTING.md).

## Correlation ID

Every CI run is keyed by **`workflow_run_id`** (GitHub Actions run id) or the equivalent id passed into Google Workflows. Use it to find:

- **GCS:** `triggers/plans/<workflow_run_id>.json`, `triggers/summaries/<workflow_run_id>/...`, ephemeral `triggers/reporting/<workflow_run_id>.json` (see [architecture.md](architecture.md))
- **GCP:** Workflow execution in the Google Cloud console (URL may be recorded under `triggers/reporting/` for Check Run details)
- **Logs:** Cloud Run job logs for `bmt-control` (plan/coordinator) and `bmt-task-standard` / `bmt-task-heavy` (task legs)

## Where to look first

1. **GitHub** — Workflow run for `build-and-test` / handoff; commit status and Check Run for the BMT context.
2. **Workflows execution** — Failed plan, task, or coordinator stage; task index and profile (standard vs heavy).
3. **GCS** — Plan file present; per-leg summaries present; snapshots under `projects/<project>/results/<bmt_slug>/snapshots/<run_id>/`.
4. **Ephemeral `triggers/`** — Removed only after the coordinator persists **`github_publish_complete`** (GitHub check finalize + commit status). If publish never completes, objects may remain by design for forensics.

## Orphaned `triggers/` and handoff concurrency

### Symptom: objects left under `triggers/` after a run

- **Logs:** Search Cloud Logging for **`bmt_coordinator_cleanup_skipped`** with `reason=github_publish_incomplete`, or **`bmt_github_publish_blocked`** when legs passed on disk but GitHub publish could not be confirmed.
- **Meaning:** GCS may already show updated **`current.json`** / snapshots while GitHub checks or status are stale. Ephemeral plan, summaries, progress, and reporting JSON are **intentionally retained** until publish completes so you can re-run diagnostics or manual finalize.
- **Cleanup:** Delete the `triggers/` subtree for that `workflow_run_id` once you no longer need it, or add a **bucket lifecycle rule** on prefix `triggers/` (for example age **14 days**) in your infra repo / Pulumi stack so abandoned runs do not grow without bound.

### `bmt-handoff.yml` concurrency

The reusable workflow [`.github/workflows/bmt-handoff.yml`](../../.github/workflows/bmt-handoff.yml) uses **`cancel-in-progress: true`**. Two overlapping invocations on the **same concurrency group** can cancel an in-flight handoff mid-step, risking **partial uploads** or confusing partial state. Mitigations: reduce push churn on hot branches; or set **`cancel-in-progress: false`** only if the org accepts overlapping handoffs (higher cost / duplicate work).

## Orphaned `triggers/` and handoff concurrency

Ephemeral objects under `triggers/plans/`, `triggers/reporting/`, `triggers/summaries/` should be removed after a successful coordinator publish. If coordinator exits early (GitHub API failure, superseded run, workflow abort), objects may remain until manual cleanup or bucket lifecycle rules.

### PR-first lifecycle (default for PR handoffs)

When handoff carries a **PR number**, the active run is recorded at:

`gs://$GCS_BUCKET/triggers/pr-active/{owner}/{repo}/pr-{N}.json`

Fields include `active_generation`, `github_workflow_run_id`, `gcp_execution_name`, and `github_check_run_id`. A superseded run logs `bmt_run_superseded` and skips plan/task/coordinator GitHub finalize.

**Debug:** compare registry `github_workflow_run_id` + `active_generation` to `triggers/plans/{workflow_run_id}.json` on the suspect run.

**Cleanup (dry-run default):** `uv run python tools/bmt/pr_registry_cleanup.py --bucket $GCS_BUCKET` (add `--apply` to delete).

**Archive folders:** rollback trees such as `projects/sk.previous/` must not keep `enabled: true` with a live `project` slug and shared `results_prefix` — that duplicates plan legs. Either disable those manifests or rely on planner archive-dir ignore (flat layout only).

### `bmt-handoff.yml` concurrency

The reusable workflow uses **`cancel-in-progress: true`**. PR-scoped groups dedupe by **`inputs.pr_number`**; overlapping runs on the same PR cancel in-flight handoff steps. Registry cancel handles GCP supersede for the same PR.

## Common symptoms

| Symptom | Likely checks |
| ------- | ------------- |
| Stuck **pending** status | Coordinator never ran; GitHub API finalize failed; see **§11.3** in [architecture.md](architecture.md) (Maintainer deep dive) |
| Gate shows fail but bucket looks pass (or reverse) | Split-brain between GitHub and GCS; compare `ci_verdict.json` vs Check Run |
| Missing leg summary | Task crash before write; eventual consistency delay; see [architecture.md](architecture.md) weak-points sections |

## Secrets and access

- **CI → GCP:** Workload Identity Federation; no long-lived keys in Actions.
- **Runtime → GitHub:** GitHub App installation tokens from **Secret Manager** (see [configuration.md](configuration.md)).

Do **not** paste tokens, private keys, or bucket URLs with embedded credentials into public issues. Follow your company’s internal channel for reporting sensitive issues.

## Related docs

- [configuration.md](configuration.md) — Env vars, Pulumi, branch protection
- [architecture.md](architecture.md) — Pipeline, diagrams, maintainer risks and remediation index
