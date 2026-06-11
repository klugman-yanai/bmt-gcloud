from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from cloud_bmt import gate_verify
from cloud_bmt.config import BmtConfig


def test_discover_projects_from_checkout(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "sk"
    project_dir.mkdir(parents=True)
    (project_dir / "wake_word_quality.json").write_text(
        json.dumps({"enabled": True, "inputs_prefix": "projects/sk/inputs/wake_word_quality"}),
        encoding="utf-8",
    )
    (project_dir / "project.json").write_text("{}", encoding="utf-8")

    assert gate_verify.discover_projects_from_checkout(tmp_path / "projects") == ["sk"]


def test_resolve_projects_from_csv() -> None:
    assert gate_verify.resolve_projects(explicit="sk,lgtv", stage_root=None) == ["sk", "lgtv"]


def test_resolve_projects_from_repo_checkout(tmp_path: Path, monkeypatch: Any) -> None:
    (tmp_path / "cloud-ci-handoff").mkdir()
    (tmp_path / "projects" / "lgtv").mkdir(parents=True)
    monkeypatch.chdir(tmp_path / "cloud-ci-handoff")
    (tmp_path / "projects" / "lgtv" / "kws.json").write_text(
        json.dumps({"enabled": True, "inputs_prefix": "projects/lgtv/inputs/kws"}),
        encoding="utf-8",
    )
    assert gate_verify.resolve_projects(explicit=None, stage_root=None) == ["lgtv"]


def test_discover_projects_from_gate_bucket(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        gate_verify.gcs,
        "list_prefix",
        lambda _uri: [
            "gs://demo-bucket/projects/sk/project.json",
            "gs://demo-bucket/projects/lgtv/project.json",
        ],
    )
    assert gate_verify.discover_projects_from_gate_bucket("demo-bucket") == ["lgtv", "sk"]


def test_verify_gate_readiness_passes_with_mocks(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    stage_root = tmp_path / "stage"
    project_dir = stage_root / "projects" / "sk"
    project_dir.mkdir(parents=True)
    (project_dir / "wake_word_quality.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "inputs_prefix": "projects/sk/inputs/wake_word_quality",
                "files": [{"name": "a.wav"}, {"name": "b.wav"}],
            }
        ),
        encoding="utf-8",
    )

    def _exists(uri: str) -> bool:
        if "cloud_bench_runner" in uri or uri.endswith("/plugin.py"):
            return True
        return uri.endswith(("a.wav", "b.wav"))

    monkeypatch.setattr(gate_verify.gcs, "object_exists", _exists)
    monkeypatch.setattr(
        gate_verify.gcs,
        "list_prefix",
        lambda uri: (
            [
                "gs://demo-bucket/projects/sk/inputs/wake_word_quality/a.wav",
                "gs://demo-bucket/projects/sk/inputs/wake_word_quality/b.wav",
            ]
            if "wake_word_quality" in uri
            else []
        ),
    )
    monkeypatch.setattr(gate_verify.gcs, "download_json", lambda _uri: ({}, None))
    monkeypatch.setattr(gate_verify, "_object_mode_is_executable", lambda *_a, **_k: True)

    cfg = BmtConfig.model_construct(gcs_bucket="demo-bucket")
    report = gate_verify.verify_gate_readiness(
        cfg,
        gate_verify.GateVerifyOptions(
            bucket="demo-bucket",
            projects=["sk"],
            stage_root=stage_root,
            check_prepared_cache=False,
        ),
    )
    assert report.ok


def test_verify_gate_readiness_reports_missing_runner(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    stage_root = tmp_path / "stage"
    project_dir = stage_root / "projects" / "lgtv"
    project_dir.mkdir(parents=True)
    (project_dir / "kws.json").write_text(
        json.dumps({"enabled": True, "inputs_prefix": "projects/lgtv/inputs/kws"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(gate_verify.gcs, "object_exists", lambda _uri: False)
    monkeypatch.setattr(gate_verify.gcs, "list_prefix", lambda _uri: [])
    monkeypatch.setattr(gate_verify.gcs, "download_json", lambda _uri: ({"plugins": {}}, None))

    cfg = BmtConfig.model_construct(gcs_bucket="demo-bucket")
    report = gate_verify.verify_gate_readiness(
        cfg,
        gate_verify.GateVerifyOptions(
            bucket="demo-bucket",
            projects=["lgtv"],
            stage_root=stage_root,
        ),
    )
    assert not report.ok
    assert any("runner missing" in err for err in report.errors)


def test_run_verify_raises_on_errors(monkeypatch: Any) -> None:
    monkeypatch.setenv("GCS_BUCKET", "demo-bucket")
    monkeypatch.setenv("ACCEPTED_PROJECTS", '["lgtv"]')
    monkeypatch.setattr(
        gate_verify,
        "verify_gate_readiness",
        lambda *_a, **_k: gate_verify.GateVerifyReport(errors=["boom"]),
    )
    cfg = BmtConfig.model_construct(gcs_bucket="demo-bucket")
    with pytest.raises(RuntimeError, match="Gate verify failed"):
        gate_verify.run_verify(cfg)
