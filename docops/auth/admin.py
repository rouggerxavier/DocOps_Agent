"""Admin access helpers."""

from __future__ import annotations

import os

from docops.auth.security import normalize_email
from docops.db.models import User


def _parse_admin_emails() -> set[str]:
    raw = str(os.getenv("ADMIN_EMAILS") or "").strip()
    if not raw:
        return set()
    items = {
        normalize_email(item)
        for item in raw.split(",")
        if item and str(item).strip()
    }
    return {item for item in items if item}


def is_admin_email(email: str | None) -> bool:
    normalized = normalize_email(str(email or ""))
    if not normalized:
        return False
    return normalized in _parse_admin_emails()


def is_admin_user(user: User) -> bool:
    if bool(getattr(user, "is_admin", False)):
        return True
    return is_admin_email(getattr(user, "email", None))

