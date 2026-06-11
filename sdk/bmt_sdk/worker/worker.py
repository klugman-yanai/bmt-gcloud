"""Worker interface for plugin hook execution."""

from __future__ import annotations

from typing import Protocol

from bmt_sdk.worker.contracts import (
    EvaluateRequest,
    EvaluateResponse,
    ExecuteRequest,
    ExecuteResponse,
    PrepareRequest,
    PrepareResponse,
    ScoreRequest,
    ScoreResponse,
)
from bmt_sdk.worker.descriptor import PluginDescriptor


class PluginWorker(Protocol):
    def describe(self) -> PluginDescriptor: ...
    def prepare(self, request: PrepareRequest) -> PrepareResponse: ...
    def execute(self, request: ExecuteRequest) -> ExecuteResponse: ...
    def score(self, request: ScoreRequest) -> ScoreResponse: ...
    def evaluate(self, request: EvaluateRequest) -> EvaluateResponse: ...
