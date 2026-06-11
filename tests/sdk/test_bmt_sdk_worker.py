"""SDK worker contract and versioning tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from bmt_sdk.worker import (
    AbiIncompatibleError,
    PluginCapabilities,
    PluginDescriptor,
    WorkerContextEnvelope,
    ensure_abi_compatible,
)
from pydantic import ValidationError


def test_plugin_descriptor_requires_minimum_fields() -> None:
    descriptor = PluginDescriptor(
        plugin_id="sk.keyword",
        plugin_slug="keyword",
        project="sk",
        plugin_version="2.0.0",
        plugin_api_version="2.0",
        entrypoint="sk_keyword.worker:Worker",
        capabilities=PluginCapabilities(network_profile="allowlisted", secrets_scope=["sk-api"]),
    )
    assert descriptor.capabilities.network_profile == "allowlisted"


def test_worker_context_envelope_is_strict() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        WorkerContextEnvelope.model_validate(
            {
                "workspace_root": Path("/tmp/ws"),
                "dataset_root": Path("/tmp/data"),
                "outputs_root": Path("/tmp/out"),
                "logs_root": Path("/tmp/logs"),
                "plugin_root": Path("/tmp/plugin"),
                "bmt_slug": "false_alarms",
                "unknown_key": True,
            }
        )


def test_ensure_abi_compatible_major_and_minor_rules() -> None:
    ensure_abi_compatible(runtime_api_version="2.3", plugin_api_version="2.1")
    with pytest.raises(AbiIncompatibleError, match="major"):
        ensure_abi_compatible(runtime_api_version="2.3", plugin_api_version="1.9")
    with pytest.raises(AbiIncompatibleError, match="newer than runtime"):
        ensure_abi_compatible(runtime_api_version="2.3", plugin_api_version="2.4")
