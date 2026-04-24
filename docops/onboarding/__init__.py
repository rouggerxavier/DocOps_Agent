"""Onboarding tour domain package.

Provides the static catalog of onboarding steps, event vocabulary and
derivation helpers. See `docs/onboarding/spec.md` for the design document.
"""

from docops.onboarding.catalog import (
    EVENT_TYPES,
    IDEMPOTENT_EVENT_TYPES,
    ONBOARDING_SCHEMA_VERSION,
    OnboardingSection,
    OnboardingStep,
    SECTIONS,
    catalog_sections,
    get_section,
    get_step,
    is_known_event_type,
    is_known_section,
    is_known_step,
    required_step_ids,
    total_step_count,
)

__all__ = [
    "EVENT_TYPES",
    "IDEMPOTENT_EVENT_TYPES",
    "ONBOARDING_SCHEMA_VERSION",
    "OnboardingSection",
    "OnboardingStep",
    "SECTIONS",
    "catalog_sections",
    "get_section",
    "get_step",
    "is_known_event_type",
    "is_known_section",
    "is_known_step",
    "required_step_ids",
    "total_step_count",
]
