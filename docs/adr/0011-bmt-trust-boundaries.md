# ADR 0011: BMT trust boundaries for workflow inputs

## Status

Accepted

## Context

Cloud BMT **`WorkflowRequest`** fields (for example `GITHUB_REPOSITORY`, `BMT_HEAD_SHA`, `BMT_ACCEPTED_PROJECTS_JSON`) are populated from **GitHub Actions** environment variables by the **handoff** workflow and passed into Cloud Run. The runtime uses them to select the GitHub repository for Checks / status APIs and to build **`ExecutionPlan`** metadata. **PyGithub** installation tokens are chosen using **`github_app_profile_for_repository`** (org vs dev profile by repo owner).

## Decision

1. **Caller trust is organizational:** only **trusted** repositories should call **`bmt-handoff.yml`** via `workflow_call` / dispatch with secrets and variables configured for production.
2. **Shape validation:** `WorkflowRequest` validates **non-empty** `repository` as `owner/name` and **non-empty** `head_sha` as **40 hex characters** (empty allowed for local-only flows). Malformed values **fail fast** at plan construction instead of producing partial GitHub API calls.
3. **Fork / non-org repos** continue to use the **dev** GitHub App credential profile keyed off repository owner; production org workloads use the **primary** profile.

## Consequences

- Mis-set or malicious **shape** values are rejected early; **semantic** trust (which repo may invoke handoff, which SHA is “the” PR head) remains a **process and branch-protection** concern, not something the runtime can fully infer.
- Operators must keep **WIF attribute conditions**, **GitHub App** installations, and **caller** repos aligned with this model.

## References

- `runtime/models.py` — `WorkflowRequest` validators
- `runtime/github/github_auth.py` — `github_app_profile_for_repository`
- [configuration.md](../configuration.md) — env and repo variables
