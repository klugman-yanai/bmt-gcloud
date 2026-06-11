"""Plugin identity defaults."""

from __future__ import annotations

from runtime.plugin_contract import (
    DEFAULT_PLUGIN_VERSION,
    default_plugin_id,
    resolve_plugin_id,
    resolve_plugin_version,
)

pytestmark = __import__("pytest").mark.unit


def test_default_plugin_id() -> None:
    assert default_plugin_id("sk") == "sk.default"


def test_resolve_plugin_id_uses_default() -> None:
    assert resolve_plugin_id("skyworth", None) == "skyworth.default"
    assert resolve_plugin_id("skyworth", "") == "skyworth.default"
    assert resolve_plugin_id("skyworth", "skyworth.keyword") == "skyworth.keyword"


def test_resolve_plugin_version_default() -> None:
    assert resolve_plugin_version(None) == DEFAULT_PLUGIN_VERSION
    assert resolve_plugin_version("") == DEFAULT_PLUGIN_VERSION
    assert resolve_plugin_version("3.0.0") == "3.0.0"

