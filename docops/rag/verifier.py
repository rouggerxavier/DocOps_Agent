"""Grounding verifier: checks that answers are properly cited and evidence-backed."""

import re
from typing import TYPE_CHECKING

from docops.config import config
from docops.logging import get_logger
from docops.rag.citations import count_citations_in_answer, max_citation_index

if TYPE_CHECKING:
    from docops.graph.state import AgentState

logger = get_logger("docops.rag.verifier")

_CITATION_INDEX_RE = re.compile(r"\[Fonte\s*\d+\]", re.IGNORECASE)
_NON_FACTUAL_HINT_RE = re.compile(
    r"\b("
    r"nao\s+encontrei|não\s+encontrei|"
    r"nao\s+sei|não\s+sei|"
    r"sem\s+informac\w+|"
    r"insuficient\w+|"
    r"nao\s+tenho\s+dados|não\s+tenho\s+dados|"
    r"pode\s+esclarecer|poderia\s+esclarecer"
    r")\b",
    re.IGNORECASE,
)
_ACK_ONLY_RE = re.compile(
    r"^(ok|ok[,.\s]*entendido|entendido|certo|beleza|perfeito|thanks|obrigad[oa])"
    r"[.!]?$",
    re.IGNORECASE,
)
_FACTUAL_HINT_RE = re.compile(
    r"\b\d{4}\b|"
    r"\b\d+(?:[.,]\d+)?\s*%|"
    r"\b(segundo|conforme|de\s+acordo\s+com|define-se|defined\s+as|according\s+to)\b",
    re.IGNORECASE,
)

_FACTUAL_CHECK_PROMPT = """\
Você é um classificador de respostas. Determine se a resposta abaixo contém afirmações factuais que requerem citação de fontes.

Uma resposta FACTUAL contém: fatos, dados, números, datas, definições, resultados, atribuições, relações causais.
Uma resposta NÃO-FACTUAL contém: "não sei", "não encontrei", perguntas de volta, pedidos de esclarecimento, respostas vazias.

Responda APENAS com "factual" ou "nao_factual", sem nenhum texto adicional.

RESPOSTA:
{answer}"""


def _heuristic_is_factual(answer: str) -> bool:
    text = re.sub(r"\s+", " ", (answer or "").strip())
    if not text:
        return False
    if _ACK_ONLY_RE.match(text):
        return False
    if _NON_FACTUAL_HINT_RE.search(text):
        return False
    if _CITATION_INDEX_RE.search(text):
        return True
    if _FACTUAL_HINT_RE.search(text):
        return True
    return len(text) > 40 and "?" not in text


def _llm_is_factual(answer: str, *, fallback: bool) -> bool:
    """Use LLM to determine if the answer contains factual claims requiring citations."""
    try:
        from langchain_core.messages import HumanMessage
        from docops.llm.router import build_chat_model
        from docops.llm.content import response_text

        llm = build_chat_model(route="cheap", temperature=0.0)
        response = llm.invoke(
            [HumanMessage(content=_FACTUAL_CHECK_PROMPT.format(answer=answer[:2000]))]
        )
        raw = response_text(response).strip().lower()
        return "nao_factual" not in raw
    except Exception as exc:
        logger.warning(
            f"LLM factual check failed ({exc}); using heuristic fallback={fallback}."
        )
        return fallback


def is_factual_answer(answer: str) -> bool:
    """Determine if the answer contains factual claims that require citations."""
    mode = (config.grounded_verifier_mode or "heuristic").lower()
    heuristic = _heuristic_is_factual(answer)

    if mode == "heuristic":
        return heuristic
    if mode == "hybrid":
        if not heuristic:
            return False
        return _llm_is_factual(answer, fallback=heuristic)
    return _llm_is_factual(answer, fallback=heuristic)


def has_min_citations(answer: str, min_cites: int | None = None) -> bool:
    """Check whether the answer has at least min_cites [Fonte N] references."""
    required = min_cites if min_cites is not None else config.min_citations
    found = count_citations_in_answer(answer)
    return found >= required


def verify_grounding(state: "AgentState") -> dict:
    """Verify that the synthesized answer is properly grounded.

    Returns a dict with:
    - ``grounding_ok``: bool — True if verification passed
    - ``retry``: bool — True if we should retry with higher top_k
    - ``disclaimer``: str — message to append if evidence is weak
    """
    answer = state.get("answer", "")
    retry_count = state.get("retry_count", 0)

    # Short circuit: if there are no retrieved docs, it can't be grounded
    chunks = state.get("retrieved_chunks", [])
    if not chunks:
        logger.warning("No retrieved chunks — grounding check fails.")
        return {
            "grounding_ok": False,
            "retry": retry_count < config.max_retries,
            "disclaimer": (
                "\n\n> ⚠️ **Aviso:** Não foram encontrados trechos relevantes nos documentos "
                "indexados. Verifique se os documentos corretos foram inseridos e tente "
                "reformular sua pergunta."
            ),
        }

    # Check if answer is factual and needs citations
    factual = is_factual_answer(answer)
    cites_ok = has_min_citations(answer)

    if not factual:
        # Non-factual answer (e.g., "I don't know", clarification question) — no citation required
        logger.debug("Answer is non-factual; grounding check passes.")
        return {"grounding_ok": True, "retry": False, "disclaimer": ""}

    # Check for phantom citations: [Fonte N] where N > number of chunks
    max_idx = max_citation_index(answer)
    if max_idx > len(chunks):
        logger.warning(
            f"Phantom citation detected: [Fonte {max_idx}] but only {len(chunks)} chunks."
        )
        if retry_count < config.max_retries:
            return {"grounding_ok": False, "retry": True, "disclaimer": ""}
        return {
            "grounding_ok": False,
            "retry": False,
            "disclaimer": (
                "\n\n> ⚠️ **Aviso:** A resposta referencia fontes inexistentes. "
                "Os resultados podem não ser confiáveis."
            ),
        }

    if cites_ok:
        logger.debug("Answer has sufficient citations; grounding check passes.")
        return {"grounding_ok": True, "retry": False, "disclaimer": ""}

    # Factual answer but missing citations
    found_cites = count_citations_in_answer(answer)
    logger.warning(
        f"Grounding check failed: found {found_cites} citation(s), "
        f"need {config.min_citations}. retry_count={retry_count}"
    )

    if retry_count < config.max_retries:
        return {
            "grounding_ok": False,
            "retry": True,
            "disclaimer": "",
        }

    # Max retries exhausted
    return {
        "grounding_ok": False,
        "retry": False,
        "disclaimer": (
            "\n\n> ⚠️ **Aviso de baixa evidência:** Esta resposta pode não estar "
            "completamente suportada pelos documentos disponíveis. "
            "Considere adicionar mais documentos relevantes ou reformular a consulta."
        ),
    }
