"""Feature capability endpoint for frontend gating."""

from __future__ import annotations

import os

from fastapi import APIRouter

from docops.api.schemas import CapabilitiesResponse
from docops.features.flags import all_feature_flags

router = APIRouter()


def _parse_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in ("true", "1", "yes", "on")


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities() -> CapabilitiesResponse:
    flags = all_feature_flags()
    return CapabilitiesResponse(
        flags=flags,
        map={item["key"]: bool(item["enabled"]) for item in flags},
        disable_all=_parse_bool(os.getenv("FEATURE_FLAGS_DISABLE_ALL"), default=False),
        enable_all=_parse_bool(os.getenv("FEATURE_FLAGS_ENABLE_ALL"), default=False),
    )
