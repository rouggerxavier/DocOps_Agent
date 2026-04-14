"""Unit tests for premium entitlement resolution and enforcement."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from docops.features.entitlements import (
    entitlements_enabled,
    is_capability_allowed,
    locked_feature_detail,
    require_capability,
    resolve_user_tier,
)


_ENTITLEMENT_ENV_KEYS = [
    "FEATURE_FLAGS",
    "FEATURE_FLAGS_ENABLE_ALL",
    "FEATURE_FLAGS_DISABLE_ALL",
    "FEATURE_PREMIUM_ENTITLEMENTS_ENABLED",
    "PREMIUM_DEFAULT_TIER",
    "PREMIUM_USER_TIER_OVERRIDES",
    "PREMIUM_ENTITLED_USER_IDS",
    "PREMIUM_ENTITLED_EMAILS",
]


@pytest.fixture(autouse=True)
def _clean_entitlement_env(monkeypatch: pytest.MonkeyPatch):
    for key in _ENTITLEMENT_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    for key in _ENTITLEMENT_ENV_KEYS:
        os.environ.pop(key, None)


def _user(user_id: int = 1, email: str = "tester@example.com") -> SimpleNamespace:
    return SimpleNamespace(id=user_id, email=email)


def test_entitlement_enforcement_disabled_keeps_capabilities_open():
    user = _user()
    assert entitlements_enabled() is False
    assert is_capability_allowed("premium_chat_to_artifact", user) is True
    assert is_capability_allowed("premium_artifact_templates", user) is True


def test_entitlement_enforcement_blocks_free_tier(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FEATURE_PREMIUM_ENTITLEMENTS_ENABLED", "true")
    monkeypatch.setenv("PREMIUM_DEFAULT_TIER", "free")
    user = _user()

    assert entitlements_enabled() is True
    assert resolve_user_tier(user) == "free"
    assert is_capability_allowed("premium_chat_to_artifact", user) is False

    detail = locked_feature_detail("premium_chat_to_artifact", user)
    assert detail["error"] == "feature_locked"
    assert detail["code"] == "premium_capability_required"
    assert detail["required_tier"] == "premium"
    assert detail["current_tier"] == "free"

    with pytest.raises(HTTPException) as exc:
        require_capability("premium_chat_to_artifact", user)
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "feature_locked"


def test_entitled_user_id_grants_premium(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FEATURE_PREMIUM_ENTITLEMENTS_ENABLED", "true")
    monkeypatch.setenv("PREMIUM_DEFAULT_TIER", "free")
    monkeypatch.setenv("PREMIUM_ENTITLED_USER_IDS", "1,99")
    user = _user(user_id=1)

    assert resolve_user_tier(user) == "premium"
    assert is_capability_allowed("premium_personalization", user) is True


def test_explicit_user_tier_overrides_take_precedence(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FEATURE_PREMIUM_ENTITLEMENTS_ENABLED", "true")
    monkeypatch.setenv("PREMIUM_DEFAULT_TIER", "free")
    monkeypatch.setenv(
        "PREMIUM_USER_TIER_OVERRIDES",
        "email:tester@example.com=enterprise,id:7=free",
    )

    assert resolve_user_tier(_user(user_id=1, email="tester@example.com")) == "enterprise"
    assert resolve_user_tier(_user(user_id=7, email="another@example.com")) == "free"
