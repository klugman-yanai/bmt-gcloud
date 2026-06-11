"""Plugin worker SDK contracts and hook interfaces."""

from bmt_sdk.worker.contracts import (
    EvaluateRequest,
    EvaluateResponse,
    ExecuteRequest,
    ExecuteResponse,
    PluginInvocation,
    PrepareRequest,
    PrepareResponse,
    ScoreRequest,
    ScoreResponse,
    WorkerContextEnvelope,
)
from bmt_sdk.worker.descriptor import PluginCapabilities, PluginDescriptor
from bmt_sdk.worker.host_api import HttpClient, SecretProvider, StorageClient, TelemetrySink, WorkerHostApi
from bmt_sdk.worker.policies import (
    aggregate_mean_ok_cases,
    build_case_outcomes,
    normalize_comparison,
    score_direction_hint,
    score_direction_label,
    scoring_policy_record,
)
from bmt_sdk.worker.versions import AbiIncompatibleError, ParsedApiVersion, ensure_abi_compatible
from bmt_sdk.worker.worker import PluginWorker

__all__ = [
    "AbiIncompatibleError",
    "EvaluateRequest",
    "EvaluateResponse",
    "ExecuteRequest",
    "ExecuteResponse",
    "HttpClient",
    "ParsedApiVersion",
    "PluginCapabilities",
    "PluginDescriptor",
    "PluginInvocation",
    "PluginWorker",
    "PrepareRequest",
    "PrepareResponse",
    "ScoreRequest",
    "ScoreResponse",
    "SecretProvider",
    "StorageClient",
    "TelemetrySink",
    "WorkerContextEnvelope",
    "WorkerHostApi",
    "aggregate_mean_ok_cases",
    "build_case_outcomes",
    "ensure_abi_compatible",
    "normalize_comparison",
    "score_direction_hint",
    "score_direction_label",
    "scoring_policy_record",
]
