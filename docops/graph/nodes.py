"""LangGraph node functions — each takes AgentState and returns a partial state update."""

from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from docops.config import config
from docops.llm.content import response_text
from docops.llm.router import build_chat_model
from docops.logging import get_logger
from docops.rag.citations import build_context_block, build_sources_section
from docops.rag.prompts import (
    INTENT_CLASSIFICATION_PROMPT,
    RAG_SYNTHESIS_PROMPT,
    BRIEF_SUMMARY_PROMPT,
    DEEP_SUMMARY_PROMPT,
    COMPARISON_PROMPT,
    STUDY_PLAN_PROMPT,
    GROUNDING_REPAIR_PROMPT,
    SYSTEM_PROMPT,
)
from docops.rag.retriever import retrieve_for_doc
from docops.rag.verifier import verify_grounding
from docops.tools.doc_tools import tool_search_docs
from docops.graph.state import AgentState

logger = get_logger("docops.graph.nodes")


def _get_llm(
    *,
    route: str = "qa_simple",
    intent: str | None = None,
    summary_mode: str | None = None,
    temperature: float = 0.2,
):
    """Create a Gemini LLM instance using deterministic route selection."""
    return build_chat_model(
        route=route,
        intent=intent,
        summary_mode=summary_mode,
        temperature=temperature,
    )


# ── Node 1: classify_intent ─────────────────────────────────────────────────

def classify_intent(state: AgentState) -> dict[str, Any]:
    """Classify the user's query into an intent category."""
    query = state["query"]
    logger.info(f"Classifying intent for: '{query[:80]}'")

    prompt = INTENT_CLASSIFICATION_PROMPT.format(query=query)
    llm = _get_llm(route="cheap", temperature=0.0)

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        intent = response_text(response).lower().split()[0]
        # Validate against known intents
        valid = {"qa", "summary", "comparison", "checklist", "study_plan", "artifact", "other"}
        if intent not in valid:
            intent = "qa"
    except Exception as exc:
        logger.warning(f"Intent classification failed ({exc}); defaulting to 'qa'")
        intent = "qa"

    logger.info(f"Intent: {intent}")
    return {"intent": intent}


# ── Node 2: retrieve ────────────────────────────────────────────────────────

def retrieve_node(state: AgentState) -> dict[str, Any]:
    """Retrieve relevant chunks from the user's vector store via tool_search_docs."""
    query = state["query"]
    user_id = state.get("user_id", 0)
    top_k = state.get("top_k", config.top_k)
    extra = state.get("extra", {}) or {}
    doc_name = extra.get("doc_name")
    doc_id = extra.get("doc_id")

    if doc_name and state.get("intent") in ("summary", "comparison"):
        logger.info(f"Retrieving all chunks from '{doc_name}' for user {user_id}, {state.get('intent')}")
        chunks = retrieve_for_doc(
            doc_name,
            query=query,
            top_k=200,
            user_id=user_id,
            doc_id=str(doc_id) if doc_id else None,
        )
    else:
        logger.info(f"Retrieving top_k={top_k} chunks for user {user_id}, query: '{query[:60]}'")
        chunks = tool_search_docs(query, user_id=user_id, top_k=top_k)

    if not chunks:
        logger.warning("No chunks retrieved — will produce standard 'not found' response.")

    context_block = build_context_block(chunks)
    return {
        "retrieved_chunks": chunks,
        "context_block": context_block,
    }


# ── Node 3: synthesize ──────────────────────────────────────────────────────

def synthesize(state: AgentState) -> dict[str, Any]:
    """Synthesize an answer from retrieved chunks using the LLM."""
    intent = state.get("intent", "qa")
    query = state["query"]
    context_block = state.get("context_block", "")
    extra = state.get("extra", {}) or {}

    summary_mode = str(extra.get("summary_mode", "brief")).lower()
    llm = _get_llm(
        route="graph_synthesize",
        intent=intent,
        summary_mode=summary_mode,
        temperature=0.2,
    )
    logger.info(f"Synthesizing answer (intent={intent}, summary_mode={summary_mode})")

    # Pick the right prompt based on intent
    if intent == "summary":
        doc_name = extra.get("doc_name", "documento")
        prompt_template = DEEP_SUMMARY_PROMPT if summary_mode == "deep" else BRIEF_SUMMARY_PROMPT
        user_prompt = prompt_template.format(context=context_block, doc_name=doc_name)
        logger.info(f"Summary mode: {summary_mode}")
    elif intent == "comparison":
        doc1 = extra.get("doc1", "Documento 1")
        doc2 = extra.get("doc2", "Documento 2")
        context2 = extra.get("context2", "")
        user_prompt = COMPARISON_PROMPT.format(
            context1=context_block,
            context2=context2,
            doc1=doc1,
            doc2=doc2,
        )
    elif intent == "study_plan":
        topic = extra.get("topic", query)
        user_prompt = STUDY_PLAN_PROMPT.format(context=context_block, topic=topic)
    else:
        user_prompt = RAG_SYNTHESIS_PROMPT.format(context=context_block, query=query)

    try:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]
        response = llm.invoke(messages)
        raw_answer = response_text(response)
    except Exception as exc:
        logger.error(f"LLM synthesis failed: {exc}")
        raw_answer = (
            "Ocorreu um erro ao processar sua solicitação. "
            "Verifique sua GEMINI_API_KEY e tente novamente."
        )

    return {"raw_answer": raw_answer, "answer": raw_answer}


# ── Node 4: verify_grounding ─────────────────────────────────────────────────

def _semantic_grounding_payload(answer: str, chunks: list) -> dict:
    """Compute semantic grounding support against retrieved evidence chunks."""
    from docops.grounding.claims import extract_claims, extract_cited_claims
    from docops.grounding.support import compute_support_rate

    cited_claims = extract_cited_claims(answer)
    claims = [c["claim"] for c in cited_claims] if cited_claims else extract_claims(answer)
    support = compute_support_rate(
        claims,
        chunks,
        mode=config.grounded_verifier_mode,
    )
    return {
        **support,
        "claims_checked": len(claims),
        "mode": config.grounded_verifier_mode,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _repair_answer(state: AgentState, unsupported_claims: list[str]) -> str:
    """Repair answer by keeping only claims that are supported by context."""
    llm = _get_llm(route="qa_simple", temperature=0.2)
    claims_block = "\n".join(f"- {c}" for c in unsupported_claims) or "- (none)"
    prompt = GROUNDING_REPAIR_PROMPT.format(
        query=state.get("query", ""),
        answer=state.get("raw_answer", state.get("answer", "")),
        unsupported_claims=claims_block,
        context=state.get("context_block", ""),
    )
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]
    response = llm.invoke(messages)
    return response_text(response)

def verify_grounding_node(state: AgentState) -> dict[str, Any]:
    """Check that the answer is properly grounded in the retrieved documents.

    Also runs semantic claim→evidence verification when
    SEMANTIC_GROUNDING_ENABLED=true, and triggers a repair pass if the
    CitationSupportRate falls below MIN_SUPPORT_RATE.
    """
    result = verify_grounding(state)
    update: dict[str, Any] = {**result}
    logger.info(
        f"Grounding: ok={result['grounding_ok']}, retry={result['retry']}, "
        f"retry_count={state.get('retry_count', 0)}, repair_count={state.get('repair_count', 0)}"
    )

    if not config.semantic_grounding_enabled:
        return update

    # Semantic claim verification is only meaningful for open QA.
    # For summary/comparison, the LLM synthesizes directly from the full doc context,
    # so claim-level scoring produces systematic false negatives.
    intent = state.get("intent", "qa")
    if intent in ("summary", "comparison"):
        return update

    answer = state.get("answer", "")
    chunks = state.get("retrieved_chunks", [])
    if not answer or not chunks:
        return update

    try:
        grounding_info = _semantic_grounding_payload(answer, chunks)
        update["grounding_info"] = grounding_info
        update["grounding"] = grounding_info
        support_rate = float(grounding_info.get("support_rate", 1.0))
        logger.info(
            f"Semantic grounding: support_rate={support_rate:.2f}, "
            f"claims={grounding_info.get('claims_checked', 0)}, "
            f"unsupported={len(grounding_info.get('unsupported_claims', []))}"
        )
    except Exception as exc:
        logger.warning(f"Semantic grounding check failed: {exc}")
        return update

    if support_rate >= config.min_support_rate:
        return update

    # Try one repair pass first.
    repair_count = int(state.get("repair_count", 0))
    if repair_count < config.grounding_repair_max_passes:
        try:
            repaired = _repair_answer(
                state,
                list(grounding_info.get("unsupported_claims", [])),
            )
            if repaired:
                logger.info("Applying semantic repair pass to answer.")
                update["raw_answer"] = repaired
                update["answer"] = repaired
                update["repair_count"] = repair_count + 1

                repaired_state = dict(state)
                repaired_state.update({"raw_answer": repaired, "answer": repaired})
                repaired_basic = verify_grounding(repaired_state)  # type: ignore[arg-type]
                update.update(repaired_basic)

                repaired_grounding = _semantic_grounding_payload(repaired, chunks)
                update["grounding_info"] = repaired_grounding
                update["grounding"] = repaired_grounding
                repaired_rate = float(repaired_grounding.get("support_rate", 1.0))

                if repaired_rate >= config.min_support_rate:
                    update["grounding_ok"] = True
                    update["retry"] = False
                    return update
        except Exception as exc:
            logger.warning(f"Repair pass failed: {exc}")

    # Optional retrieval retry (limited) when support remains low.
    if (
        not update.get("retry", False)
        and int(state.get("retry_count", 0)) < config.grounding_retrieval_max_retries
    ):
        logger.warning(
            f"Support below threshold ({config.min_support_rate}); "
            "triggering retrieval retry."
        )
        update["retry"] = True
        update["grounding_ok"] = False
        return update

    # No retry left: return with disclaimer.
    disclaimer = str(update.get("disclaimer", ""))
    low_support_msg = (
        "\n\n> ⚠️ **Aviso:** A resposta foi limitada a evidências parcialmente suportadas "
        "pelos documentos disponíveis."
    )
    if low_support_msg not in disclaimer:
        disclaimer += low_support_msg
    update["disclaimer"] = disclaimer
    update["grounding_ok"] = False
    update["retry"] = False
    return update


# ── Node 5: retry_retrieve ──────────────────────────────────────────────────

def retry_retrieve(state: AgentState) -> dict[str, Any]:
    """Increment top_k and retry_count before re-running retrieval."""
    current_top_k = state.get("top_k", config.top_k)
    current_retry = state.get("retry_count", 0)
    new_top_k = current_top_k + 4  # fetch more docs on retry

    logger.info(f"Retrying retrieval: top_k {current_top_k} → {new_top_k}")
    return {
        "top_k": new_top_k,
        "retry_count": current_retry + 1,
        "retry": False,
    }


# ── Node 6: finalize ────────────────────────────────────────────────────────

def finalize(state: AgentState) -> dict[str, Any]:
    """Build the final answer: raw_answer + disclaimer + sources section."""
    raw_answer = state.get("raw_answer", "")
    disclaimer = state.get("disclaimer", "")
    chunks = state.get("retrieved_chunks", [])
    query = state.get("query", "")

    sources_section = build_sources_section(chunks, query=query)
    final_answer = raw_answer + disclaimer

    # Append sources if not already present in the answer
    if "**Fontes:**" not in final_answer and sources_section:
        final_answer = final_answer.rstrip() + "\n\n" + sources_section

    logger.info("Answer finalized.")
    return {
        "answer": final_answer,
        "sources_section": sources_section,
    }
