"""Capability broker used by worker-hosted plugins."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from bmt_sdk.worker.host_api import HttpClient, SecretProvider, StorageClient, TelemetrySink, WorkerHostApi


class _NoopSecrets(SecretProvider):
    def get_secret(self, key: str) -> str:
        raise KeyError(f"Secret {key!r} is not available in this runtime")


class _NoopStorage(StorageClient):
    def read_text(self, uri: str) -> str:
        return Path(uri).read_text(encoding="utf-8")

    def write_text(self, uri: str, data: str) -> None:
        Path(uri).write_text(data, encoding="utf-8")


class _NoopHttp(HttpClient):
    def get_json(self, url: str, *, timeout_seconds: int) -> Mapping[str, object]:
        raise RuntimeError("HTTP capability is not configured for this plugin runtime")

    def post_json(self, url: str, payload: Mapping[str, object], *, timeout_seconds: int) -> Mapping[str, object]:
        raise RuntimeError("HTTP capability is not configured for this plugin runtime")


class _NoopTelemetry(TelemetrySink):
    def emit_event(self, name: str, fields: Mapping[str, object]) -> None:
        del name, fields


class CapabilityBroker(WorkerHostApi):
    """Default capability broker with explicit no-op/fail-closed behavior."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.secrets = _NoopSecrets()
        self.storage = _NoopStorage()
        self.http = _NoopHttp()
        self.telemetry = _NoopTelemetry()
