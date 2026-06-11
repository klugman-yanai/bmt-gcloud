"""Strict Pydantic models for plugin configuration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictPluginModel(BaseModel):
    """Strict immutable base for plugin developer configuration models."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class ManifestConfig(StrictPluginModel):
    """Common validated ``plugin_config`` fields for bench manifests."""

    comparison: str = "gte"
    tolerance_abs: float = Field(default=0.25, ge=0.0)
    run_notes: list[str] = Field(default_factory=list)
    reporting_hints: dict[str, object] = Field(default_factory=dict)


class ScoringPolicyRecord(BaseModel):
    """Validated scoring metadata consumed by reporting and verdict evaluation."""

    model_config = ConfigDict(strict=True, extra="allow", frozen=True)

    comparison: str
    score_direction_hint: str
    score_direction_label: str = Field(min_length=1)
    keyword: str | None = None
    reducer: str | None = None
    failure_policy: str | None = None
    tolerance_abs: float | None = Field(default=None, ge=0.0)

    @classmethod
    def from_mapping(cls, payload: dict[str, object]) -> ScoringPolicyRecord:
        return cls.model_validate(dict(payload))

    def as_dict(self) -> dict[str, object]:
        return self.model_dump(mode="python")
