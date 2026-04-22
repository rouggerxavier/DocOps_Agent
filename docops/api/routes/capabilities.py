"""Feature capability endpoint for frontend gating."""

from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi import Depends

from docops.api.schemas import CapabilitiesResponse
from docops.auth.dependencies import get_current_user
from docops.db.models import User
from docops.features.entitlements import entitlement_snapshot_for_user
from docops.features.flags import all_feature_flags

router = APIRouter()


def _parse_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in ("true", "1", "yes", "on")


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities(
    current_user: User = Depends(get_current_user),
) -> CapabilitiesResponse:
    flags = all_feature_flags()
    entitlement_snapshot = entitlement_snapshot_for_user(current_user)
    return CapabilitiesResponse(
        flags=flags,
        map={item["key"]: bool(item["enabled"]) for item in flags},
        disable_all=_parse_bool(os.getenv("FEATURE_FLAGS_DISABLE_ALL"), default=False),
        enable_all=_parse_bool(os.getenv("FEATURE_FLAGS_ENABLE_ALL"), default=False),
        entitlements_enabled=bool(entitlement_snapshot.get("enabled")),
        entitlement_tier=str(entitlement_snapshot.get("tier") or "free"),
        entitlement_map=dict(entitlement_snapshot.get("map") or {}),
        entitlement_capabilities=list(entitlement_snapshot.get("capabilities") or []),
    )
