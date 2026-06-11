"""GCS operations using google-cloud-storage. One client per process."""

from __future__ import annotations

import functools
import json
import re
from typing import Any

from google.api_core import exceptions as api_exceptions
from google.cloud import storage

# gs://bucket-name/path/to/object
_GS_URI = re.compile(r"^gs://([^/]+)/(.*)$")


class GcsError(RuntimeError):
    """Raised when a GCS operation fails in a non-recoverable way."""


@functools.lru_cache(maxsize=1)
def _client_singleton() -> storage.Client:
    """Single client per process (uses default credentials, e.g. WIF in Actions)."""
    return storage.Client()


def _get_client() -> storage.Client:
    """Return the process-wide GCS client."""
    return _client_singleton()


def parse_gs_uri(uri: str) -> tuple[str, str]:
    """Parse gs://bucket/path to (bucket_name, blob_path). Raises ValueError if invalid."""
    m = _GS_URI.match(uri.strip())
    if not m:
        raise ValueError(f"Invalid GCS URI: {uri!r}")
    bucket_name, path = m.group(1), m.group(2)
    if not bucket_name:
        raise ValueError(f"Invalid GCS URI (empty bucket): {uri!r}")
    return bucket_name, path.strip("/") or ""


def read_object(uri: str) -> bytes:
    """Download a GCS object as raw bytes. Raises GcsError on failure."""
    try:
        bucket_name, path = parse_gs_uri(uri)
        client = _get_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(path)
        return blob.download_as_bytes()
    except ValueError as exc:
        raise GcsError(str(exc)) from exc
    except Exception as exc:
        raise GcsError(f"Failed to read {uri}: {exc}") from exc


def write_object(uri: str, data: bytes | str) -> None:
    """Upload raw bytes or str to GCS. Raises GcsError on failure."""
    try:
        bucket_name, path = parse_gs_uri(uri)
        client = _get_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(path)
        if isinstance(data, str):
            data = data.encode("utf-8")
        blob.upload_from_string(data)
    except ValueError as exc:
        raise GcsError(str(exc)) from exc
    except Exception as exc:
        raise GcsError(f"Failed to write {uri}: {exc}") from exc


def list_prefix(prefix_uri: str) -> list[str]:
    """List blob names under gs://bucket/prefix (returns full gs:// URIs)."""
    try:
        bucket_name, prefix_path = parse_gs_uri(prefix_uri)
        client = _get_client()
        bucket = client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix=prefix_path)
        out: list[str] = []
        for b in blobs:
            if b.name:
                out.append(f"gs://{bucket_name}/{b.name}")
        return out
    except ValueError as exc:
        raise GcsError(str(exc)) from exc
    except Exception as exc:
        raise GcsError(f"Failed to list {prefix_uri}: {exc}") from exc


def copy_object(src_uri: str, dest_uri: str) -> None:
    """Copy a GCS object within the same bucket."""
    try:
        src_bucket, src_path = parse_gs_uri(src_uri)
        dest_bucket, dest_path = parse_gs_uri(dest_uri)
        if src_bucket != dest_bucket:
            raise GcsError(f"Cross-bucket copy not supported: {src_uri} -> {dest_uri}")
        client = _get_client()
        bucket = client.bucket(src_bucket)
        src_blob = bucket.blob(src_path)
        if not src_blob.exists():
            return
        bucket.copy_blob(src_blob, bucket, dest_path)
    except ValueError as exc:
        raise GcsError(str(exc)) from exc
    except Exception as exc:
        raise GcsError(f"Failed to copy {src_uri} -> {dest_uri}: {exc}") from exc


def delete_object(uri: str) -> None:
    """Delete a GCS object. Raises GcsError on failure (not on 404)."""
    try:
        bucket_name, path = parse_gs_uri(uri)
        client = _get_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(path)
        blob.delete()
    except ValueError as exc:
        raise GcsError(str(exc)) from exc
    except api_exceptions.NotFound:
        return  # already deleted; treat as success
    except Exception as exc:
        raise GcsError(f"Failed to delete {uri}: {exc}") from exc


def object_exists(uri: str) -> bool:
    """Return True if the GCS object exists.

    Raises :exc:`ValueError` for invalid ``gs://`` URIs. Propagates :exc:`GcsError` on
    GCS/network/auth failures so callers do not treat infrastructure errors as "missing".
    """
    try:
        bucket_name, path = parse_gs_uri(uri)
        client = _get_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(path)
        return blob.exists()
    except ValueError:
        raise
    except Exception as exc:
        raise GcsError(f"Failed to check existence of {uri}: {exc}") from exc


def upload_json(uri: str, payload: dict[str, Any]) -> None:
    """Upload a JSON object to GCS. Raises GcsError on failure."""
    data = json.dumps(payload, indent=2) + "\n"
    write_object(uri, data)


def read_object_with_generation(uri: str) -> tuple[bytes, int | None]:
    """Download object bytes and GCS generation (None when object does not exist)."""
    try:
        bucket_name, path = parse_gs_uri(uri)
        client = _get_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(path)
        if not blob.exists():
            return b"", None
        blob.reload()
        return blob.download_as_bytes(), blob.generation
    except ValueError as exc:
        raise GcsError(str(exc)) from exc
    except Exception as exc:
        raise GcsError(f"Failed to read {uri}: {exc}") from exc


def upload_json_if_generation(
    uri: str,
    payload: dict[str, Any],
    *,
    expected_generation: int | None,
) -> int:
    """Upload JSON with a generation precondition. Returns new blob generation.

    ``expected_generation=None`` creates only when absent (if_generation_match=0).
    ``expected_generation=int`` replaces only that generation.
    """
    try:
        bucket_name, path = parse_gs_uri(uri)
        client = _get_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(path)
        data = json.dumps(payload, indent=2) + "\n"
        if expected_generation is None:
            blob.upload_from_string(data, if_generation_match=0)
        else:
            blob.upload_from_string(data, if_generation_match=expected_generation)
        blob.reload()
        gen = blob.generation
        if gen is None:
            raise GcsError(f"Upload succeeded but generation missing for {uri}")
        return int(gen)
    except api_exceptions.PreconditionFailed as exc:
        raise GcsError(f"CAS precondition failed for {uri}") from exc
    except ValueError as exc:
        raise GcsError(str(exc)) from exc
    except GcsError:
        raise
    except Exception as exc:
        raise GcsError(f"Failed to CAS-write {uri}: {exc}") from exc


def download_json(uri: str) -> tuple[dict[str, Any] | None, str | None]:
    """Download a GCS object as JSON; return (payload, None) or (None, error_message)."""
    try:
        raw = read_object(uri)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            return None, "invalid_json: expected object"
        return payload, None
    except GcsError as exc:
        return None, str(exc)
    except json.JSONDecodeError as exc:
        return None, f"invalid_json: {exc}"
    except Exception as exc:
        return None, str(exc)
