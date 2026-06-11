"""Check Run progress publish cadence (env + periodic mid-leg updates)."""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from runtime.config import constants as runtime_constants
from runtime.models import ExecutionPlan, StageRuntimePaths

logger = logging.getLogger(__name__)


def resolved_check_run_detail_publish_interval_sec() -> int:
    """Wall-clock seconds between mid-leg ``publish_progress`` calls; ``0`` = milestones only."""
    raw = (os.environ.get(runtime_constants.ENV_BMT_CHECK_RUN_DETAIL_PUBLISH_INTERVAL_SEC) or "").strip()
    interval = runtime_constants.BMT_CHECK_RUN_DETAIL_PUBLISH_INTERVAL_SEC_DEFAULT
    if not raw:
        return interval
    try:
        parsed = int(raw, 10)
    except ValueError:
        return interval
    return parsed if parsed >= 0 else interval


@contextmanager
def periodic_check_run_progress(
    *,
    plan: ExecutionPlan,
    runtime: StageRuntimePaths,
    interval_sec: int | None = None,
) -> Iterator[None]:
    """While a leg runs, refresh the GitHub Check Run on a fixed interval when enabled."""
    interval = resolved_check_run_detail_publish_interval_sec() if interval_sec is None else interval_sec
    if interval <= 0:
        yield
        return

    stop = threading.Event()

    def _loop() -> None:
        from runtime.github_reporting import publish_progress

        while not stop.wait(interval):
            try:
                publish_progress(plan=plan, runtime=runtime)
            except Exception:
                logger.warning(
                    "periodic publish_progress failed workflow_run_id=%s",
                    plan.workflow_run_id,
                    exc_info=True,
                )

    thread = threading.Thread(target=_loop, name="bmt-check-progress", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=float(interval) + 5.0)
