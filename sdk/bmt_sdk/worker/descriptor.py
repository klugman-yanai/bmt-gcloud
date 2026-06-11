"""Plugin descriptor and capability models for registry discovery."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PluginDescriptorModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class PluginCapabilities(PluginDescriptorModel):
    network_profile: Literal["none", "allowlisted", "full"] = "none"
    secrets_scope: list[str] = Field(default_factory=list)
    storage_scope: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=900, ge=1)
    retry_budget: int = Field(default=0, ge=0, le=10)


class PluginDescriptor(PluginDescriptorModel):
    plugin_id: str = Field(min_length=1)
    plugin_slug: str = Field(min_length=1)
    project: str = Field(min_length=1)
    plugin_version: str = Field(min_length=1)
    plugin_api_version: str = Field(min_length=1)
    entrypoint: str = Field(min_length=1, description="Python import path, e.g. pkg.module:Worker")
    capabilities: PluginCapabilities = PluginCapabilities()
