"""Minimal GCS JSON helpers for baseline (no cloud_bmt import)."""

from __future__ import annotations

import json
import re
from typing import Any

from google.cloud import storage

_GS_URI = re.compile(r"^gs://([^/]+)/(.*)$")


def download_json(uri: str) -> tuple[dict[str, Any] | None, str | None]:
    m = _GS_URI.match(uri.strip())
    if not m:
        return None, f"invalid uri: {uri}"
    bucket_name, path = m.group(1), m.group(2)
    try:
        client = storage.Client()
        blob = client.bucket(bucket_name).blob(path)
        if not blob.exists():
            return None, "not found"
        raw = blob.download_as_bytes()
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            return None, "expected object"
        return payload, None
    except Exception as exc:
        return None, str(exc)


def upload_json(uri: str, payload: dict[str, Any]) -> None:
    m = _GS_URI.match(uri.strip())
    if not m:
        raise ValueError(f"invalid uri: {uri}")
    bucket_name, path = m.group(1), m.group(2)
    data = json.dumps(payload, indent=2) + "\n"
    client = storage.Client()
    client.bucket(bucket_name).blob(path).upload_from_string(data.encode("utf-8"))
