"""Tests for BMT runner matrix contract mapping."""

from __future__ import annotations

import pytest
from cloud_bmt.matrix import _build_bmt_rows, _build_ci_rows

pytestmark = pytest.mark.unit


def test_bmt_runner_rows_use_suite_contracts_and_skip_unmapped_presets() -> None:
    rows = _build_bmt_rows(
        [
            {"name": "SEI_ROBOTICS_gcc_Release", "binaryDir": "${sourceDir}/build/SEI_ROBOTICS/gcc_Release"},
            {"name": "SK_gcc_Release", "binaryDir": "${sourceDir}/build/SK/gcc_Release"},
            {"name": "KT_GG4_gcc_Release", "binaryDir": "${sourceDir}/build/KT_GG4/gcc_Release"},
        ]
    )["include"]

    assert [(row["project"], row["preset"]) for row in rows] == [
        ("freebox", "sei_robotics_gcc_release"),
        ("sk", "sk_gcc_release"),
    ]
    assert rows[1]["build"] == "SK_gcc_Release-build"
    assert rows[1]["artifact_name"] == "runner-SK_gcc_Release-build"


def test_bmt_runner_rows_use_build_presets_for_artifact_names() -> None:
    rows = _build_bmt_rows(
        [{"name": "SK_gcc_Release", "binaryDir": "${sourceDir}/build/SK/gcc_Release"}],
        {"SK_gcc_Release": "custom-sk-build"},
    )["include"]

    assert rows == [
        {
            "project": "sk",
            "preset": "sk_gcc_release",
            "configure": "SK_gcc_Release",
            "build": "custom-sk-build",
            "artifact_name": "runner-custom-sk-build",
            "runner_path": "build/SK/gcc_Release/Runners/cloud_bench_runner",
            "lib_path": "build/SK/gcc_Release/Cloud Bench/libCloud Bench.so",
        }
    ]


def test_ci_rows_use_build_presets_for_artifact_names() -> None:
    rows = _build_ci_rows(
        [{"name": "SK_gcc_Release", "binaryDir": "${sourceDir}/build/SK/gcc_Release"}],
        {"SK_gcc_Release": "custom-sk-build"},
    )

    assert rows == [{"configure": "SK_gcc_Release", "build": "custom-sk-build", "short": "SK_gcc_Release"}]
