# bmt-sdk

Plugin author guide: [`../../docs/plugins.md`](../../docs/plugins.md).

Typical runner plugin:

```python
from __future__ import annotations

from bmt_sdk import BmtPlugin, direct_4ch, cloud_bench_runner


def plugin() -> BmtPlugin:
    return cloud_bench_runner(project="my-oem", audio=direct_4ch(), keyword="score")
```

Install: `pip install bmt-sdk` (or use the in-repo copy under `cloud-ci-handoff/sdk/`).
