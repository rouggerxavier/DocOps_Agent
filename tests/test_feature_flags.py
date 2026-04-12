"""Unit tests for centralized feature flags."""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

from docops.features.flags import (
    feature_flag_map,
    is_feature_enabled,
    parse_feature_flags_csv,
    require_feature_enabled,
)


_FLAG_ENV_KEYS = [
    "FEATURE_FLAGS",
    "FEATURE_FLAGS_ENABLE_ALL",
    "FEATURE_FLAGS_DISABLE_ALL",
    "FEATURE_CHAT_STREAMING_ENABLED",
    "FEATURE_STRICT_GROUNDING_ENABLED",
    "FEATURE_PREMIUM_TRUST_LAYER_ENABLED",
    "FEATURE_PREMIUM_ARTIFACT_TEMPLATES_ENABLED",
    "FEATURE_PERSONALIZATION_ENABLED",
    "FEATURE_PROACTIVE_COPILOT_ENABLED",
    "FEATURE_PREMIUM_ENTITLEMENTS_ENABLED",
]


@pytest.fixture(autouse=True)
def _clean_flag_env(monkeypatch: pytest.MonkeyPatch):
    for key in _FLAG_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    for key in _FLAG_ENV_KEYS:
        os.environ.pop(key, None)


def test_parse_feature_flags_csv():
    parsed = parse_feature_flags_csv(
        "chat_streaming_enabled=true,premium_trust_layer_enabled=false,bad-entry"
    )
    assert parsed["chat_streaming_enabled"] is True
    assert parsed["premium_trust_layer_enabled"] is False
    assert "bad-entry" not in parsed


def test_default_flags_have_expected_baseline():
    flags = feature_flag_map()
    assert flags["chat_streaming_enabled"] is True
    assert flags["strict_grounding_enabled"] is True
    assert flags["premium_trust_layer_enabled"] is False


def test_single_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FEATURE_CHAT_STREAMING_ENABLED", "false")
    assert is_feature_enabled("chat_streaming_enabled") is False


def test_csv_override_takes_precedence_over_single_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FEATURE_CHAT_STREAMING_ENABLED", "false")
    monkeypatch.setenv("FEATURE_FLAGS", "chat_streaming_enabled=true")
    assert is_feature_enabled("chat_streaming_enabled") is True


def test_disable_all_has_highest_precedence(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FEATURE_FLAGS_ENABLE_ALL", "true")
    monkeypatch.setenv("FEATURE_FLAGS_DISABLE_ALL", "true")
    assert is_feature_enabled("chat_streaming_enabled") is False
    assert is_feature_enabled("premium_trust_layer_enabled") is False


def test_enable_all_enables_premium_flags(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FEATURE_FLAGS_ENABLE_ALL", "true")
    assert is_feature_enabled("premium_trust_layer_enabled") is True
    assert is_feature_enabled("personalization_enabled") is True


def test_require_feature_enabled_raises_http_exception(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FEATURE_CHAT_STREAMING_ENABLED", "false")
    with pytest.raises(HTTPException) as exc:
        require_feature_enabled("chat_streaming_enabled")
    assert exc.value.status_code == 503
