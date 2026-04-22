"""Premium entitlement matrix and backend enforcement helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from docops.features.flags import is_feature_enabled, require_feature_enabled


_ENTITLEMENTS_FLAG_KEY = "premium_entitlements_enabled"
_DEFAULT_TIER_ENV = "PREMIUM_DEFAULT_TIER"
_USER_TIER_OVERRIDES_ENV = "PREMIUM_USER_TIER_OVERRIDES"
_ENTITLED_USER_IDS_ENV = "PREMIUM_ENTITLED_USER_IDS"
_ENTITLED_EMAILS_ENV = "PREMIUM_ENTITLED_EMAILS"

_TIER_ORDER = {
    "free": 0,
    "premium": 1,
    "enterprise": 2,
}


@dataclass(frozen=True)
class EntitlementDefinition:
    key: str
    description: str
    required_tier: str = "premium"


_ENTITLEMENT_DEFS: tuple[EntitlementDefinition, ...] = (
    EntitlementDefinition(
        key="premium_artifact_templates",
        description="Use advanced artifact templates (exam pack and deep dossier).",
        required_tier="premium",
    ),
    EntitlementDefinition(
        key="premium_chat_to_artifact",
        description="Save deep chat responses into linked artifacts.",
        required_tier="premium",
    ),
    EntitlementDefinition(
        key="premium_personalization",
        description="Read and manage persisted personalization preferences.",
        required_tier="premium",
    ),
    EntitlementDefinition(
        key="premium_proactive_copilot",
        description="Access proactive recommendation endpoints.",
        required_tier="premium",
    ),
)

_ENTITLEMENT_INDEX = {item.key: item for item in _ENTITLEMENT_DEFS}
_PREMIUM_TEMPLATE_IDS = {"exam_pack", "deep_dossier"}


def _parse_csv_items(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {item.strip() for item in raw.split(",") if item.strip()}


def _normalize_tier(raw: str | None) -> str:
    tier = str(raw or "").strip().lower()
    if tier in _TIER_ORDER:
        return tier
    return "free"


def _parse_user_tier_overrides(raw: str | None) -> tuple[dict[str, str], dict[str, str]]:
    by_id: dict[str, str] = {}
    by_email: dict[str, str] = {}
    if not raw:
        return by_id, by_email

    for item in raw.split(","):
        token = item.strip()
        if not token or "=" not in token:
            continue
        selector, tier_raw = token.split("=", 1)
        selector = selector.strip().lower()
        tier = _normalize_tier(tier_raw)
        if not selector:
            continue
        if selector.startswith("id:"):
            key = selector[3:].strip()
            if key:
                by_id[key] = tier
            continue
        if selector.startswith("email:"):
            key = selector[6:].strip()
            if key:
                by_email[key] = tier
            continue
        if selector.isdigit():
            by_id[selector] = tier
            continue
        if "@" in selector:
            by_email[selector] = tier

    return by_id, by_email


def _resolve_user_id(user: Any) -> str | None:
    value = getattr(user, "id", None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _resolve_user_email(user: Any) -> str | None:
    value = getattr(user, "email", None)
    text = str(value or "").strip().lower()
    return text or None


def entitlements_enabled() -> bool:
    return is_feature_enabled(_ENTITLEMENTS_FLAG_KEY)


def entitlement_definitions() -> list[EntitlementDefinition]:
    return list(_ENTITLEMENT_DEFS)


def resolve_user_tier(user: Any) -> str:
    user_id = _resolve_user_id(user)
    user_email = _resolve_user_email(user)

    by_id, by_email = _parse_user_tier_overrides(os.getenv(_USER_TIER_OVERRIDES_ENV))
    if user_id and user_id in by_id:
        return by_id[user_id]
    if user_email and user_email in by_email:
        return by_email[user_email]

    entitled_ids = _parse_csv_items(os.getenv(_ENTITLED_USER_IDS_ENV))
    if user_id and user_id in entitled_ids:
        return "premium"

    entitled_emails = {item.lower() for item in _parse_csv_items(os.getenv(_ENTITLED_EMAILS_ENV))}
    if user_email and user_email in entitled_emails:
        return "premium"

    return _normalize_tier(os.getenv(_DEFAULT_TIER_ENV, "free"))


def is_premium_template(template_id: str | None) -> bool:
    return str(template_id or "").strip() in _PREMIUM_TEMPLATE_IDS


def is_capability_allowed(capability_key: str, user: Any) -> bool:
    definition = _ENTITLEMENT_INDEX.get(capability_key)
    if definition is None:
        return False
    if not entitlements_enabled():
        return True

    current_tier = resolve_user_tier(user)
    current_rank = _TIER_ORDER.get(current_tier, 0)
    required_rank = _TIER_ORDER.get(definition.required_tier, _TIER_ORDER["premium"])
    return current_rank >= required_rank


def entitlement_map_for_user(user: Any) -> dict[str, bool]:
    return {definition.key: is_capability_allowed(definition.key, user) for definition in _ENTITLEMENT_DEFS}


def entitlement_snapshot_for_user(user: Any) -> dict[str, Any]:
    tier = resolve_user_tier(user)
    capability_map = entitlement_map_for_user(user)
    return {
        "enabled": entitlements_enabled(),
        "tier": tier,
        "map": capability_map,
        "capabilities": [
            {
                "key": definition.key,
                "enabled": capability_map.get(definition.key, False),
                "required_tier": definition.required_tier,
                "description": definition.description,
            }
            for definition in _ENTITLEMENT_DEFS
        ],
    }


def locked_feature_detail(
    capability_key: str,
    user: Any,
    *,
    message: str | None = None,
) -> dict[str, Any]:
    definition = _ENTITLEMENT_INDEX.get(capability_key)
    current_tier = resolve_user_tier(user)
    required_tier = definition.required_tier if definition else "premium"
    description = definition.description if definition else "Premium capability is required."
    return {
        "error": "feature_locked",
        "code": "premium_capability_required",
        "message": message or description,
        "capability": capability_key,
        "required_tier": required_tier,
        "current_tier": current_tier,
    }


def require_capability(
    capability_key: str,
    user: Any,
    *,
    status_code: int = 403,
    message: str | None = None,
) -> None:
    if not entitlements_enabled():
        return

    if is_capability_allowed(capability_key, user):
        return

    raise HTTPException(
        status_code=status_code,
        detail=locked_feature_detail(capability_key, user, message=message),
    )


def require_feature_and_capability(
    feature_key: str,
    capability_key: str,
    user: Any,
    *,
    feature_status_code: int = 503,
    capability_status_code: int = 403,
    feature_disabled_detail: str | None = None,
    capability_message: str | None = None,
) -> None:
    """Standard backend-first premium guard for flagged + entitled features."""
    require_feature_enabled(
        feature_key,
        status_code=feature_status_code,
        detail=feature_disabled_detail,
    )
    require_capability(
        capability_key,
        user,
        status_code=capability_status_code,
        message=capability_message,
    )
