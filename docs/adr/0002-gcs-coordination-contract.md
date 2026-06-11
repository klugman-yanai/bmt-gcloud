# ADR 0002: GCS coordination contract

## Status

Accepted

## Context

The pipeline has no shared database. **Google Cloud Storage** holds:

- Frozen **plans** and per-leg **summaries** under `triggers/`
- **Snapshots** and **`current.json`** pointers under each project’s `results/` tree

Workers must agree on **paths**, **ordering**, and **cleanup** without transactions.

## Decision

Treat the bucket (mirroring the materialized **`cloud-ci-handoff/generated/stage`** tree) as the **single coordination plane**:

- Ephemeral objects under `triggers/` for the active run
- Persistent results under `projects/.../results/...`
- **Coordinator** is the single writer for pointer updates and ephemeral cleanup after tasks complete (per workflow design)

## Consequences

- **Positive:** Simple, inspectable artifacts; works with standard GCS tooling
- **Negative:** Must document invariants and test edge cases for partial failure and retries.

## References

- [developer-workflow.md](../developer-workflow.md)
- [docs/architecture.md](../architecture.md#maintainer-deep-dive) — GCS coordination model and weak points
