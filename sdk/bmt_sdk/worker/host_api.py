"""Host capability interfaces exposed to plugin workers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol


class SecretProvider(Protocol):
    def get_secret(self, key: str) -> str: ...


class StorageClient(Protocol):
    def read_text(self, uri: str) -> str: ...
    def write_text(self, uri: str, data: str) -> None: ...


class HttpClient(Protocol):
    def get_json(self, url: str, *, timeout_seconds: int) -> Mapping[str, object]: ...
    def post_json(self, url: str, payload: Mapping[str, object], *, timeout_seconds: int) -> Mapping[str, object]: ...


class TelemetrySink(Protocol):
    def emit_event(self, name: str, fields: Mapping[str, object]) -> None: ...


class WorkerHostApi(Protocol):
    secrets: SecretProvider
    storage: StorageClient
    http: HttpClient
    telemetry: TelemetrySink
    workspace_root: Path
