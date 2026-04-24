"""Centralized feature-flag registry and helpers.

This module provides:
- A single source of truth for all known feature flags.
- Runtime resolution from environment variables.
- Safe helper methods for route and service level gating.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException


def _parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in ("true", "1", "yes", "on")


def parse_feature_flags_csv(raw: str | None) -> dict[str, bool]:
    """Parse `FEATURE_FLAGS` env payload.

    Supported format:
      FEATURE_FLAGS="flag_a=true,flag_b=false"
    """
    if not raw:
        return {}
    parsed: dict[str, bool] = {}
    for part in raw.split(","):
        item = part.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        name = key.strip()
        if not name:
            continue
        parsed[name] = _parse_bool(value, default=False)
    return parsed


@dataclass(frozen=True)
class FeatureFlagDefinition:
    key: str
    env_var: str
    default_enabled: bool
    description: str
    owner: str


_FLAG_DEFS: tuple[FeatureFlagDefinition, ...] = (
    FeatureFlagDefinition(
        key="chat_streaming_enabled",
        env_var="FEATURE_CHAT_STREAMING_ENABLED",
        default_enabled=True,
        description="Enable SSE chat streaming endpoint and incremental UX.",
        owner="chat",
    ),
    FeatureFlagDefinition(
        key="strict_grounding_enabled",
        env_var="FEATURE_STRICT_GROUNDING_ENABLED",
        default_enabled=True,
        description="Enable strict grounding controls in chat UX and backend path.",
        owner="trust",
    ),
    FeatureFlagDefinition(
        key="premium_trust_layer_enabled",
        env_var="FEATURE_PREMIUM_TRUST_LAYER_ENABLED",
        default_enabled=False,
        description="Enable premium trust/evidence UX and policies.",
        owner="trust",
    ),
    FeatureFlagDefinition(
        key="premium_artifact_templates_enabled",
        env_var="FEATURE_PREMIUM_ARTIFACT_TEMPLATES_ENABLED",
        default_enabled=False,
        description="Enable premium artifact template system.",
        owner="artifacts",
    ),
    FeatureFlagDefinition(
        key="premium_chat_to_artifact_enabled",
        env_var="FEATURE_PREMIUM_CHAT_TO_ARTIFACT_ENABLED",
        default_enabled=False,
        description="Enable one-click save from deep chat responses to artifacts.",
        owner="artifacts",
    ),
    FeatureFlagDefinition(
        key="personalization_enabled",
        env_var="FEATURE_PERSONALIZATION_ENABLED",
        default_enabled=False,
        description="Enable personalization and memory features.",
        owner="personalization",
    ),
    FeatureFlagDefinition(
        key="proactive_copilot_enabled",
        env_var="FEATURE_PROACTIVE_COPILOT_ENABLED",
        default_enabled=False,
        description="Enable proactive recommendation surfaces and actions.",
        owner="copilot",
    ),
    FeatureFlagDefinition(
        key="premium_entitlements_enabled",
        env_var="FEATURE_PREMIUM_ENTITLEMENTS_ENABLED",
        default_enabled=False,
        description="Enable premium capability enforcement and lock states.",
        owner="billing",
    ),
    FeatureFlagDefinition(
        key="onboarding_enabled",
        env_var="FEATURE_ONBOARDING_ENABLED",
        default_enabled=True,
        description="Enable the onboarding tour endpoints and persistence.",
        owner="onboarding",
    ),
)

_FLAG_INDEX = {item.key: item for item in _FLAG_DEFS}


class FeatureFlagDisabledError(RuntimeError):
    """Raised when a flag-guarded action is disabled."""

    def __init__(self, key: str):
        super().__init__(f"Feature '{key}' is disabled")
        self.key = key


def feature_flag_definitions() -> list[FeatureFlagDefinition]:
    return list(_FLAG_DEFS)


def _raw_overrides() -> dict[str, bool]:
    return parse_feature_flags_csv(os.getenv("FEATURE_FLAGS"))


def _enable_all() -> bool:
    return _parse_bool(os.getenv("FEATURE_FLAGS_ENABLE_ALL"), default=False)


def _disable_all() -> bool:
    return _parse_bool(os.getenv("FEATURE_FLAGS_DISABLE_ALL"), default=False)


def all_feature_flags() -> list[dict[str, Any]]:
    """Return all flags with resolved values and metadata."""
    entries: list[dict[str, Any]] = []
    for definition in _FLAG_DEFS:
        entries.append(
            {
                "key": definition.key,
                "env_var": definition.env_var,
                "default_enabled": definition.default_enabled,
                "description": definition.description,
                "owner": definition.owner,
                "enabled": is_feature_enabled(definition.key),
            }
        )
    return entries


def feature_flag_map() -> dict[str, bool]:
    return {item["key"]: bool(item["enabled"]) for item in all_feature_flags()}


def is_feature_enabled(key: str) -> bool:
    definition = _FLAG_INDEX.get(key)
    if definition is None:
        return False

    if _disable_all():
        return False
    if _enable_all():
        return True

    csv_overrides = _raw_overrides()
    if key in csv_overrides:
        return bool(csv_overrides[key])

    raw = os.getenv(definition.env_var)
    return _parse_bool(raw, default=definition.default_enabled)


def require_feature_enabled(
    key: str,
    *,
    status_code: int = 503,
    detail: str | None = None,
) -> None:
    """Route-level helper to block disabled features with a standard error."""
    if is_feature_enabled(key):
        return
    raise HTTPException(
        status_code=status_code,
        detail=detail or f"Feature '{key}' is disabled by feature flag.",
    )


def ensure_feature_enabled(key: str) -> None:
    """Service-level helper that avoids HTTP-specific exceptions."""
    if not is_feature_enabled(key):
        raise FeatureFlagDisabledError(key)
