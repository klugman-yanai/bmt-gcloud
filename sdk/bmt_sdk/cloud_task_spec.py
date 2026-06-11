"""Cloud Run task sizing declarations for bench tests."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BeforeValidator, Field

from bmt_sdk.plugin_models import StrictPluginModel


class CloudTaskProfile(StrEnum):
    """Cloud Run job memory class for a bench test."""

    STANDARD = "standard"
    HEAVY = "heavy"


class BenchTest(StrEnum):
    """Bench test slug used in manifests, object storage inputs, and plugin overrides."""

    REGRESSION = "regression"
    SMOKE = "smoke"


def _normalize_test_profile_map(value: object) -> object:
    if not isinstance(value, dict):
        return value
    normalized: dict[str, CloudTaskProfile] = {}
    for key, profile in value.items():
        slug = key.value if isinstance(key, BenchTest) else str(key)
        if isinstance(profile, CloudTaskProfile):
            normalized[slug] = profile
        else:
            normalized[slug] = CloudTaskProfile(str(profile))
    return normalized


TestCloudTaskMap = Annotated[dict[str, CloudTaskProfile], BeforeValidator(_normalize_test_profile_map)]


class CloudTaskSpec(StrictPluginModel):
    """Cloud Run task size selection at plan time."""

    default: CloudTaskProfile = Field(default=CloudTaskProfile.STANDARD)
    by_test: TestCloudTaskMap = Field(default_factory=dict)

    def for_slug(self, bmt_slug: str) -> CloudTaskProfile:
        return self.by_test.get(bmt_slug, self.default)


def default_cloud_task(*, heavy_tests: frozenset[BenchTest] = frozenset({BenchTest.REGRESSION})) -> CloudTaskSpec:
    """Default sizing: heavy for selected tests, standard elsewhere."""

    return CloudTaskSpec(by_test=dict.fromkeys(heavy_tests, CloudTaskProfile.HEAVY))
