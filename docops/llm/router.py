"""Deterministic Gemini model router by task category.

Rules are explicit and configurable via environment variables in ``docops.config``.
No probabilistic/autonomous model-selection is used.
"""

from __future__ import annotations

from docops.config import config


def resolve_gemini_model(
    route: str = "default",
    *,
    intent: str | None = None,
    summary_mode: str | None = None,
) -> str:
    """Resolve the Gemini model name for a deterministic route.

    Args:
        route: High-level task route.
        intent: Optional graph intent (used by ``graph_synthesize`` route).
        summary_mode: Optional summary mode (brief/deep) for graph synthesis.
    """
    if not getattr(config, "gemini_model_router_enabled", True):
        return config.gemini_model

    normalized = (route or "default").strip().lower()
    if normalized == "complex":
        return config.gemini_model_complex
    if normalized == "cheap":
        return config.gemini_model_cheap
    if normalized == "qa_simple":
        return config.gemini_model_qa_simple
    if normalized == "graph_synthesize":
        intent_norm = (intent or "").strip().lower()
        summary_mode_norm = (summary_mode or "").strip().lower()

        if intent_norm == "qa":
            return config.gemini_model_qa_simple
        if intent_norm == "summary" and summary_mode_norm == "brief":
            return config.gemini_model_cheap
        if intent_norm in {"summary", "comparison", "study_plan", "checklist"}:
            return config.gemini_model_complex
        return config.gemini_model_qa_simple

    return config.gemini_model


def build_chat_model(
    route: str = "default",
    *,
    temperature: float = 0.2,
    intent: str | None = None,
    summary_mode: str | None = None,
):
    """Create a ChatGoogleGenerativeAI with model selected by deterministic routing."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    model = resolve_gemini_model(
        route=route,
        intent=intent,
        summary_mode=summary_mode,
    )
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=config.gemini_api_key,
        temperature=temperature,
    )
