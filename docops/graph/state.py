"""AgentState: the shared state that flows through all LangGraph nodes."""

from typing import Any, List, Optional
from typing_extensions import TypedDict

from langchain_core.documents import Document


class AgentState(TypedDict, total=False):
    """Shared state for the DocOps Agent graph.

    All fields are optional (total=False) so each node can update only
    what it changes, leaving the rest untouched.
    """

    # ── Input ──────────────────────────────────────────────────────────────
    query: str
    """Original user query."""

    # ── Classification ─────────────────────────────────────────────────────
    intent: str
    """Classified intent: qa | summary | comparison | checklist | study_plan | artifact | other"""

    # ── Retrieval ──────────────────────────────────────────────────────────
    retrieved_chunks: List[Document]
    """Chunks retrieved from the vector store."""

    top_k: int
    """Current top_k used for retrieval (may increase on retry)."""

    # ── Synthesis ──────────────────────────────────────────────────────────
    raw_answer: str
    """Answer as returned by the LLM, before verification."""

    context_block: str
    """Formatted context block (numbered sources) sent to the LLM."""

    # ── Verification ───────────────────────────────────────────────────────
    grounding_ok: bool
    """Whether the grounding check passed."""

    retry: bool
    """Whether to retry retrieval + synthesis with higher top_k."""

    retry_count: int
    """Number of retries performed so far."""

    repair_count: int
    """Number of semantic repair passes performed."""

    disclaimer: str
    """Disclaimer text to append if evidence is weak."""

    # ── Semantic grounding (Phase 3) ────────────────────────────────────────
    grounding_info: Optional[dict[str, Any]]
    """Semantic grounding results:
    {
        "support_rate": float,
        "unsupported_claims": List[str],
        "mode": str,
        "results": List[dict],
    }
    Only populated when SEMANTIC_GROUNDING_ENABLED=true.
    """

    grounding: Optional[dict[str, Any]]
    """Alias of grounding_info for API/debug consumers."""

    # ── Finalization ───────────────────────────────────────────────────────
    answer: str
    """Final answer returned to the user (raw_answer + disclaimer if any)."""

    sources_section: str
    """Formatted 'Fontes:' section."""

    # ── Extra (for special intents) ────────────────────────────────────────
    extra: Optional[dict[str, Any]]
    """Arbitrary extra data for specialized intents (e.g., doc names for comparison)."""
