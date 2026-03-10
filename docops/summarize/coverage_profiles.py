"""Coverage profile presets for deep-summary quality gating.

Profiles rebalance coverage weights depending on document style.
"""

from __future__ import annotations

from typing import Any


PROFILES: dict[str, dict[str, Any]] = {
    "balanced": {
        "weight_formula": 0.30,
        "weight_procedure": 0.30,
        "weight_example": 0.20,
        "weight_concept": 0.20,
        "concept_min_hits": 2,
        "min_score": 0.50,
    },
    "formula_heavy": {
        "weight_formula": 0.50,
        "weight_procedure": 0.20,
        "weight_example": 0.15,
        "weight_concept": 0.15,
        "concept_min_hits": 2,
        "min_score": 0.55,
    },
    "procedural": {
        "weight_formula": 0.15,
        "weight_procedure": 0.50,
        "weight_example": 0.20,
        "weight_concept": 0.15,
        "concept_min_hits": 2,
        "min_score": 0.50,
    },
    "narrative": {
        "weight_formula": 0.10,
        "weight_procedure": 0.15,
        "weight_example": 0.35,
        "weight_concept": 0.40,
        "concept_min_hits": 1,
        "min_score": 0.40,
    },
}

DEFAULT_PROFILE = "balanced"


def _safe_ratio(num: int, den: int) -> float:
    if den <= 0:
        return 0.0
    return num / den


def _auto_select(doc_name: str, signals: dict[str, Any]) -> tuple[str, str]:
    """Return (profile_name, reason) using lightweight heuristics."""
    total = int(signals.get("total_chunks", 0) or 0)
    formula_ratio = _safe_ratio(int(signals.get("formula_chunks", 0) or 0), total)
    procedure_ratio = _safe_ratio(int(signals.get("procedure_chunks", 0) or 0), total)
    example_ratio = _safe_ratio(int(signals.get("example_chunks", 0) or 0), total)
    concept_ratio = _safe_ratio(int(signals.get("concept_chunks", 0) or 0), total)

    name = (doc_name or "").lower()
    name_math = any(k in name for k in ("math", "formula", "equa", "calculo", "álgebra", "algebra"))
    name_proc = any(k in name for k in ("tutorial", "manual", "howto", "guia", "proced"))
    name_narr = any(k in name for k in ("relatorio", "report", "analise", "analysis", "artigo", "essay"))

    if (formula_ratio >= 0.45 and formula_ratio >= procedure_ratio + 0.10) or name_math:
        return "formula_heavy", f"formula_ratio={formula_ratio:.2f}"
    if procedure_ratio >= 0.30 or name_proc:
        return "procedural", f"procedure_ratio={procedure_ratio:.2f}"
    if (
        formula_ratio < 0.10
        and procedure_ratio < 0.15
        and (example_ratio + concept_ratio) >= 0.50
    ) or name_narr:
        return "narrative", f"narrative_ratio={(example_ratio + concept_ratio):.2f}"
    return DEFAULT_PROFILE, "balanced_fallback"


def resolve_coverage_profile(
    doc_name: str,
    signals: dict[str, Any],
    configured_profile: str | None = None,
) -> dict[str, Any]:
    """Resolve active coverage profile.

    Args:
        doc_name: Target document file name.
        signals: Output from ``detect_coverage_signals``.
        configured_profile: ``auto`` (default) or explicit profile name.

    Returns:
        Dict with ``name``, ``reason``, and numeric profile fields.
    """
    profile = (configured_profile or "auto").strip().lower()
    if profile and profile != "auto":
        if profile in PROFILES:
            return {"name": profile, "reason": f"override:{profile}", **PROFILES[profile]}
        return {
            "name": DEFAULT_PROFILE,
            "reason": f"unknown_override:{profile}",
            **PROFILES[DEFAULT_PROFILE],
        }

    chosen, reason = _auto_select(doc_name, signals)
    return {"name": chosen, "reason": reason, **PROFILES[chosen]}
