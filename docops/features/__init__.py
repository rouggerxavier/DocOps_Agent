"""Feature flag framework for DocOps."""

from .flags import (
    FeatureFlagDefinition,
    FeatureFlagDisabledError,
    all_feature_flags,
    ensure_feature_enabled,
    feature_flag_definitions,
    feature_flag_map,
    is_feature_enabled,
    parse_feature_flags_csv,
    require_feature_enabled,
)
from .entitlements import (
    EntitlementDefinition,
    entitlement_definitions,
    entitlement_map_for_user,
    entitlement_snapshot_for_user,
    entitlements_enabled,
    is_capability_allowed,
    is_premium_template,
    locked_feature_detail,
    require_capability,
    resolve_user_tier,
)

__all__ = [
    "FeatureFlagDefinition",
    "FeatureFlagDisabledError",
    "all_feature_flags",
    "ensure_feature_enabled",
    "feature_flag_definitions",
    "feature_flag_map",
    "is_feature_enabled",
    "parse_feature_flags_csv",
    "require_feature_enabled",
    "EntitlementDefinition",
    "entitlement_definitions",
    "entitlement_map_for_user",
    "entitlement_snapshot_for_user",
    "entitlements_enabled",
    "is_capability_allowed",
    "is_premium_template",
    "locked_feature_detail",
    "require_capability",
    "resolve_user_tier",
]
