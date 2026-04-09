"""Tests for deterministic Gemini model routing."""

from __future__ import annotations


def _clear_router_env(monkeypatch) -> None:
    for key in (
        "GEMINI_MODEL_ROUTER_ENABLED",
        "GEMINI_MODEL",
        "GEMINI_MODEL_COMPLEX",
        "GEMINI_MODEL_CHEAP",
        "GEMINI_MODEL_QA_SIMPLE",
    ):
        monkeypatch.delenv(key, raising=False)


def test_default_routes(monkeypatch):
    from docops.llm.router import resolve_gemini_model

    _clear_router_env(monkeypatch)
    assert resolve_gemini_model("complex") == "gemini-3-flash-preview"
    assert resolve_gemini_model("cheap") == "gemini-3.1-flash-lite-preview"
    assert resolve_gemini_model("qa_simple") == "gemini-2.5-flash"


def test_graph_synthesize_route_rules(monkeypatch):
    from docops.llm.router import resolve_gemini_model

    _clear_router_env(monkeypatch)
    assert (
        resolve_gemini_model("graph_synthesize", intent="qa")
        == "gemini-2.5-flash"
    )
    assert (
        resolve_gemini_model("graph_synthesize", intent="summary", summary_mode="brief")
        == "gemini-3.1-flash-lite-preview"
    )
    assert (
        resolve_gemini_model("graph_synthesize", intent="summary", summary_mode="deep")
        == "gemini-3-flash-preview"
    )
    assert (
        resolve_gemini_model("graph_synthesize", intent="comparison")
        == "gemini-3-flash-preview"
    )
    assert (
        resolve_gemini_model("graph_synthesize", intent="other")
        == "gemini-2.5-flash"
    )


def test_router_can_be_disabled(monkeypatch):
    from docops.llm.router import resolve_gemini_model

    monkeypatch.setenv("GEMINI_MODEL_ROUTER_ENABLED", "false")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-custom-fallback")

    assert resolve_gemini_model("complex") == "gemini-custom-fallback"
    assert resolve_gemini_model("cheap") == "gemini-custom-fallback"
    assert resolve_gemini_model("qa_simple") == "gemini-custom-fallback"


def test_route_env_overrides(monkeypatch):
    from docops.llm.router import resolve_gemini_model

    monkeypatch.setenv("GEMINI_MODEL_ROUTER_ENABLED", "true")
    monkeypatch.setenv("GEMINI_MODEL_COMPLEX", "gemini-x-complex")
    monkeypatch.setenv("GEMINI_MODEL_CHEAP", "gemini-x-cheap")
    monkeypatch.setenv("GEMINI_MODEL_QA_SIMPLE", "gemini-x-qa")

    assert resolve_gemini_model("complex") == "gemini-x-complex"
    assert resolve_gemini_model("cheap") == "gemini-x-cheap"
    assert resolve_gemini_model("qa_simple") == "gemini-x-qa"

