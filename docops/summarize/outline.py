"""Document outline and must-cover topic extraction for deep summary pipeline.

This module builds an evidence-derived outline of the document's major topics
from chunk metadata and content analysis. It goes beyond the existing broad
facet model by detecting concrete topic areas actually present in the source.

The outline is used to:
  1. Feed a "must-cover topics" contract into the final synthesis prompt.
  2. Evaluate whether the summary covers all major topics (not just broad facets).
  3. Trigger re-synthesis when major topics are missing.
  4. Provide honest diagnostics instead of false-positive perfect scores.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from langchain_core.documents import Document

from docops.logging import get_logger

logger = get_logger("docops.summarize.outline")

# ── Topic detection patterns ──────────────────────────────────────────────────
# These are GENERIC patterns that detect topic areas across many domains.
# They are NOT specific to any one subject (e.g., decision trees).

_TOPIC_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # Contextual framing / introduction / motivation
    ("contextual_framing", re.compile(
        r"\b(?:introdu[cç][aã]o|introduction|motiva[cç][aã]o|motivation|background"
        r"|contexto|context|hist[oó]ri[ca]|history|fundamenta[cç][aã]o|foundations?"
        r"|prel[ií]min\w+|overview|vis[aã]o\s+geral)\b",
        re.IGNORECASE,
    ), "Contextual framing / introduction"),

    # Taxonomy / classification / typology
    ("taxonomy_classification", re.compile(
        r"\b(?:taxonomi\w+|classifica[cç][aã]o|classif\w+|tipolog\w+|typolog\w+"
        r"|categoriz\w+|hierarqui\w+|hierarch\w+|família\w*|famil\w+|tipo\w+\s+de"
        r"|kinds?\s+of|types?\s+of|supervised|unsupervised|supervisiona\w+)\b",
        re.IGNORECASE,
    ), "Taxonomy / classification"),

    # Core method / algorithm construction
    ("core_method", re.compile(
        r"\b(?:algoritmo|algorithm|constru[cç][aã]o|construction|procediment\w+"
        r"|procedure|m[eé]todo|method|implementa[cç][aã]o|implementation"
        r"|heur[ií]stic\w+|greedy|guloso|recursiv\w+|recursive|top.?down|bottom.?up"
        r"|divis[aã]o|split\w*|particion\w+|partition\w+)\b",
        re.IGNORECASE,
    ), "Core method / algorithm"),

    # Selection / decision criteria
    ("selection_criteria", re.compile(
        r"\b(?:crit[eé]rio\w*|criteri\w+|sele[cç][aã]o|selection|escolha|choice"
        r"|impurez\w+|impurit\w+|entrop\w+|entropy|gini|informa[cç][aã]o\s+(?:gain|ganho)"
        r"|information\s+gain|split\s+(?:criterion|crit[eé]rio)|m[eé]tric\w+|metric\w+"
        r"|loss\s+function|fun[cç][aã]o\s+(?:de\s+)?(?:perda|custo|loss|cost))\b",
        re.IGNORECASE,
    ), "Selection / decision criteria"),

    # Regularization / pruning / complexity control
    ("regularization", re.compile(
        r"\b(?:regulariz\w+|prun\w+|poda|shrink\w+|penaliz\w+|penalt\w+"
        r"|complex\w+\s+(?:control|controle)|cost.?complex\w+|alpha\w*\s*eff\w*"
        r"|early\s+stop\w+|dropout|weight\s+decay|l[12]\s+regul\w+|lasso|ridge"
        r"|elastic\s*net|overfitt\w+|underfitt\w+|bias.?variance)\b",
        re.IGNORECASE,
    ), "Regularization / complexity control"),

    # Generalization / theoretical bounds
    ("generalization_theory", re.compile(
        r"\b(?:generaliz\w+|vc.?dimen\w+|vapnik|chervonenkis|rademacher"
        r"|pac.?learn\w+|sample\s+complex\w+|bound\w*|cota\w*|limit\w+\s+te[oó]ric\w+"
        r"|convergenc\w+|consist[eê]nc\w+|approximat\w+|universal\w+)\b",
        re.IGNORECASE,
    ), "Generalization / theoretical bounds"),

    # Validation / evaluation / tuning
    ("validation_tuning", re.compile(
        r"\b(?:valida[cç][aã]o|validation|cross.?valida\w+|k.?fold|hold.?out"
        r"|train.?test|test\s+set|conjunto\s+de\s+teste|hiperpar[aâ]metr\w+"
        r"|hyperparamet\w+|tuning|ajuste|grid\s+search|random\s+search"
        r"|bayesian\s+opt\w+|acur[aá]c\w+|accurac\w+|precis[aã]o|precision"
        r"|recall|f1.?score|auc|roc|confus\w+\s+matrix|matriz\s+(?:de\s+)?confus\w+)\b",
        re.IGNORECASE,
    ), "Validation / evaluation"),

    # Examples / applications / case studies
    ("examples_applications", re.compile(
        r"\b(?:exemplo|example|aplica[cç][aã]o|application|caso\s+(?:de\s+)?(?:uso|estudo|pr[aá]tic)"
        r"|case\s+stud\w+|use\s+case|dataset|conjunto\s+de\s+dados|benchmark"
        r"|experiment\w+|demonstra[cç][aã]o|demonstrat\w+|ilustra[cç][aã]o|illustrat\w+)\b",
        re.IGNORECASE,
    ), "Examples / applications"),

    # Model variants / extensions / ensembles
    ("model_variants", re.compile(
        r"\b(?:variant\w+|varia[cç][aã]o|extension\w+|extens[aã]o|ensemble\w*"
        r"|bagging|boosting|random\s+forest|gradient\s+boost\w+|xgboost|adaboost"
        r"|stacking|blending|combina[cç][aã]o\s+(?:de\s+)?model\w+"
        r"|model\s+combinat\w+|multi.?class|multi.?label|multi.?output)\b",
        re.IGNORECASE,
    ), "Model variants / extensions"),

    # Regression / continuous prediction
    ("regression_formulation", re.compile(
        r"\b(?:regress[aã]o|regression|predi[cç][aã]o\s+(?:cont[ií]nu|num[eé]ric)"
        r"|continuous\s+predict\w+|least\s+square\w+|m[ií]nimos\s+quadrado\w+"
        r"|mean\s+squared?\s+error|mse|rmse|mae|r.?squared|r²|coeficiente\s+de\s+determina\w+"
        r"|vari[aâ]ncia|variance\s+reduc\w+|redu[cç][aã]o\s+(?:de\s+)?vari[aâ]nc)\b",
        re.IGNORECASE,
    ), "Regression formulation"),

    # Mathematical formalization / notation
    ("math_formalization", re.compile(
        r"\b(?:formaliz\w+|nota[cç][aã]o|notation|defini[cç][aã]o\s+formal"
        r"|formal\s+defini\w+|prova|proof|teorem\w+|theorem|lema|lemma"
        r"|proposi[cç][aã]o|proposit\w+|corol[aá]rio|corollar\w+)\b"
        r"|[α-ωΑ-Ω∑∫∏√∞±∂∇]"
        r"|\b(?:argmin|argmax|sup|inf|lim)\b"
        r"|\bO\s*\([^)]+\)",
        re.IGNORECASE | re.UNICODE,
    ), "Mathematical formalization"),

    # Comparison / trade-offs / advantages
    ("comparison_tradeoffs", re.compile(
        r"\b(?:compara[cç][aã]o|comparison|trade.?off|vantag\w+|advantage\w+"
        r"|desvantag\w+|disadvantage\w+|limita[cç][aã]o|limitation\w+"
        r"|pr[oó]s?\s+(?:e|and)\s+contras?|strengths?\s+(?:and|e)\s+weakness\w+)\b",
        re.IGNORECASE,
    ), "Comparison / trade-offs"),
]

# Minimum chunk hits to consider a topic "major" (must-cover).
_DEFAULT_MAJOR_TOPIC_MIN_HITS = 2
# Minimum chunk hits for a topic to be detected at all.
_DEFAULT_TOPIC_MIN_HITS = 1

_TOPIC_PATTERN_MAP: dict[str, re.Pattern[str]] = {
    tid: pattern for tid, pattern, _label in _TOPIC_PATTERNS
}

_EXPLANATION_CUE_RE = re.compile(
    r"\b(?:define\w*|defin\w+|explain\w*|explic\w+|consist\w*|envolv\w*|"
    r"permit\w*|result\w*|basead\w*|utiliz\w*|us\w+|through|via|because|"
    r"therefore|ou\s+seja|isto\s+[eé])\b",
    re.IGNORECASE,
)

_LISTING_CUE_RE = re.compile(
    r"\b(?:menciona\w*|cita\w*|lista\w*|aborda\w*|discute\w*|covers?|"
    r"mentions?|lists?|discusses?|includes?)\b",
    re.IGNORECASE,
)


def _topic_scan_text(chunk: Document) -> str:
    """Build topic-scanning text using both content and inferred structure metadata."""
    text = str(chunk.page_content or "").strip()
    meta = chunk.metadata or {}
    section_title = str(meta.get("section_title") or "").strip()
    section_path = str(meta.get("section_path") or "").strip()

    # Include inferred headings so topic extraction benefits from PDF structure.
    heading = " ".join(part for part in (section_title, section_path) if part)
    if heading and text:
        return f"{heading}\n{text}"
    if heading:
        return heading
    return text


def _count_topic_matches(pattern: re.Pattern[str], text: str) -> int:
    """Count regex matches safely for patterns with/without capture groups."""
    return sum(1 for _ in pattern.finditer(text))


def _sentence_count(text: str) -> int:
    return len([s for s in re.split(r"[.!?]+", text) if s.strip()])


def extract_document_topics(
    chunks: list[Document],
    major_topic_min_hits: int = _DEFAULT_MAJOR_TOPIC_MIN_HITS,
) -> dict[str, Any]:
    """Extract topics from document chunks using pattern matching.

    Returns:
        Dict with:
            detected_topics: list of all detected topic IDs
            must_cover_topics: list of major topic IDs (high evidence)
            minor_topics: list of minor topic IDs (low evidence)
            topic_details: dict mapping topic_id -> {label, hits, chunks, is_major}
            outline_text: formatted text for prompt injection
    """
    topic_hits: dict[str, int] = {}
    topic_chunk_indices: dict[str, list[int]] = {}

    for i, chunk in enumerate(chunks):
        text = _topic_scan_text(chunk)
        if not text:
            continue
        for topic_id, pattern, _label in _TOPIC_PATTERNS:
            if pattern.search(text):
                topic_hits[topic_id] = topic_hits.get(topic_id, 0) + 1
                if topic_id not in topic_chunk_indices:
                    topic_chunk_indices[topic_id] = []
                topic_chunk_indices[topic_id].append(i)

    detected_topics: list[str] = []
    must_cover_topics: list[str] = []
    minor_topics: list[str] = []
    topic_details: dict[str, dict[str, Any]] = {}

    for topic_id, pattern, label in _TOPIC_PATTERNS:
        hits = topic_hits.get(topic_id, 0)
        if hits < _DEFAULT_TOPIC_MIN_HITS:
            continue

        is_major = hits >= major_topic_min_hits
        detected_topics.append(topic_id)
        if is_major:
            must_cover_topics.append(topic_id)
        else:
            minor_topics.append(topic_id)

        topic_details[topic_id] = {
            "label": label,
            "hits": hits,
            "chunk_indices": topic_chunk_indices.get(topic_id, []),
            "is_major": is_major,
        }

    return {
        "detected_topics": detected_topics,
        "must_cover_topics": must_cover_topics,
        "minor_topics": minor_topics,
        "topic_details": topic_details,
        "outline_text": _format_outline_text(must_cover_topics, minor_topics, topic_details),
    }


def _format_outline_text(
    must_cover: list[str],
    minor: list[str],
    details: dict[str, dict[str, Any]],
) -> str:
    """Format the topic outline as text for prompt injection."""
    lines: list[str] = []

    if must_cover:
        lines.append("TÓPICOS PRINCIPAIS DETECTADOS (cobertura obrigatória):")
        for tid in must_cover:
            d = details.get(tid, {})
            lines.append(f"  - {d.get('label', tid)} (evidência: {d.get('hits', 0)} chunks)")
        lines.append("")

    if minor:
        lines.append("Tópicos secundários detectados:")
        for tid in minor:
            d = details.get(tid, {})
            lines.append(f"  - {d.get('label', tid)} ({d.get('hits', 0)} chunks)")
        lines.append("")

    if must_cover:
        lines.append("CONTRATO: O resumo DEVE explicar cada tópico principal listado acima,")
        lines.append("não apenas mencionar o nome. Explicar = descrever o que é, como funciona,")
        lines.append("e por que é relevante no contexto do documento.")
    elif not must_cover and not minor:
        lines.append("Nenhum tópico temático forte detectado; priorize cobertura equilibrada do conteúdo.")

    return "\n".join(lines)


def score_topic_outline_coverage(
    summary_text: str,
    topic_info: dict[str, Any],
    min_explanation_words: int = 15,
) -> dict[str, Any]:
    """Evaluate whether the summary covers detected must-cover topics.

    Unlike the existing broad facet scoring, this checks for EXPLANATORY
    coverage — the topic must not just be mentioned by keyword, but must
    appear in a context that suggests actual explanation (paragraph with
    enough substance).

    Returns:
        Dict with:
            detected_topics: list of all topic IDs
            must_cover_topics: list of major topic IDs
            covered_topics: list of topics with explanatory coverage
            missing_topics: list of topics without adequate coverage
            weakly_covered_topics: list of topics mentioned but not explained
            topic_scores: dict mapping topic_id -> score (0.0, 0.5, 1.0)
            overall_score: float in [0, 1]
    """
    must_cover = list(topic_info.get("must_cover_topics", []))
    details = topic_info.get("topic_details", {})

    if not must_cover:
        return {
            "detected_topics": list(topic_info.get("detected_topics", [])),
            "must_cover_topics": [],
            "covered_topics": [],
            "missing_topics": [],
            "weakly_covered_topics": [],
            "topic_scores": {},
            "overall_score": 1.0,
        }

    # Split summary into paragraphs for contextual analysis.
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", summary_text) if p.strip()]
    para_topic_hits: list[set[str]] = []
    for para in paragraphs:
        matched_topics: set[str] = set()
        for tid, pat in _TOPIC_PATTERN_MAP.items():
            if pat.search(para):
                matched_topics.add(tid)
        para_topic_hits.append(matched_topics)

    covered: list[str] = []
    missing: list[str] = []
    weakly_covered: list[str] = []
    topic_scores: dict[str, float] = {}

    for topic_id in must_cover:
        pattern = _TOPIC_PATTERN_MAP.get(topic_id)
        if pattern is None:
            missing.append(topic_id)
            topic_scores[topic_id] = 0.0
            continue

        # Check if topic appears in summary with explanatory context.
        best_score = 0.0
        for para_idx, para in enumerate(paragraphs):
            if topic_id not in para_topic_hits[para_idx]:
                continue
            # Count words in paragraph (excluding citations).
            clean_para = re.sub(r"\[Fonte\s*\d+\]", "", para, flags=re.IGNORECASE)
            clean_para = re.sub(r"[#*_`\[\]>|(){}\-]", " ", clean_para)
            words = re.findall(r"\w+", clean_para)
            if not words:
                continue

            topic_match_count = _count_topic_matches(pattern, clean_para)
            multi_topic_para = len(para_topic_hits[para_idx]) >= 3
            has_explanation_cue = bool(_EXPLANATION_CUE_RE.search(clean_para))
            has_listing_cue = bool(_LISTING_CUE_RE.search(clean_para))
            sentence_count = _sentence_count(clean_para)

            # Full explanatory credit requires more than a long enumeration line.
            if (
                len(words) >= min_explanation_words
                and topic_match_count >= 1
                and (
                    has_explanation_cue
                    or sentence_count >= 2
                    or topic_match_count >= 2
                )
                and not (multi_topic_para and has_listing_cue and not has_explanation_cue)
            ):
                best_score = 1.0
                break

            # Partial credit for short/local mention.
            if len(words) >= 8 and topic_match_count >= 1:
                best_score = max(best_score, 0.5)

        topic_scores[topic_id] = best_score
        if best_score >= 1.0:
            covered.append(topic_id)
        elif best_score > 0.0:
            weakly_covered.append(topic_id)
        else:
            missing.append(topic_id)

    if must_cover:
        overall = sum(topic_scores.values()) / len(must_cover)
    else:
        overall = 1.0

    return {
        "detected_topics": list(topic_info.get("detected_topics", [])),
        "must_cover_topics": must_cover,
        "covered_topics": covered,
        "missing_topics": missing,
        "weakly_covered_topics": weakly_covered,
        "topic_scores": topic_scores,
        "overall_score": round(overall, 4),
    }


def get_topic_anchors(
    topic_info: dict[str, Any],
    chunks: list[Document],
    max_per_topic: int = 2,
) -> dict[str, list[int]]:
    """For each must-cover topic, return chunk indices with the strongest evidence.

    Used by anchor selection to ensure every major topic has citation support.
    """
    details = topic_info.get("topic_details", {})
    result: dict[str, list[int]] = {}

    for topic_id in topic_info.get("must_cover_topics", []):
        td = details.get(topic_id, {})
        indices = td.get("chunk_indices", [])[:max_per_topic]
        if indices:
            result[topic_id] = indices

    return result
