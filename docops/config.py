"""Configuration management â€” reads all settings from environment variables.

Paths like CHROMA_DIR, DOCS_DIR, and ARTIFACTS_DIR are resolved relative to
the project root (the directory containing this package), not the current
working directory. This lets you invoke `python -m docops` from any directory.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Project root = parent of the 'docops' package directory (i.e. docops-agent/)
# This is always correct regardless of the current working directory.
_project_root = Path(__file__).resolve().parent.parent

# Load .env from the project root
_dotenv_file = _project_root / ".env"
if _dotenv_file.exists():
    load_dotenv(_dotenv_file)
else:
    load_dotenv()  # fallback: search upward from CWD


def _require_env(key: str) -> str:
    """Return env var value or raise a clear error if missing."""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            f"Copy .env.example to .env and fill in your values."
        )
    return value


def _path_env(key: str, default: str) -> Path:
    """Return a resolved Path from an env var.

    Relative paths are resolved against the project root (where .env lives),
    not the current working directory.
    """
    raw = os.getenv(key, default)
    p = Path(raw)
    if p.is_absolute():
        return p
    return (_project_root / p).resolve()


class Config:
    """Central configuration object. Instantiate once and share."""

    @property
    def gemini_api_key(self) -> str:
        return _require_env("GEMINI_API_KEY")

    @property
    def chroma_dir(self) -> Path:
        return _path_env("CHROMA_DIR", "./data/chroma")

    @property
    def docs_dir(self) -> Path:
        return _path_env("DOCS_DIR", "./docs")

    @property
    def uploads_dir(self) -> Path:
        return _path_env("UPLOADS_DIR", "./uploads")

    @property
    def artifacts_dir(self) -> Path:
        return _path_env("ARTIFACTS_DIR", "./artifacts")

    @property
    def top_k(self) -> int:
        return int(os.getenv("TOP_K", "6"))

    @property
    def chunk_size(self) -> int:
        return int(os.getenv("CHUNK_SIZE", "900"))

    @property
    def chunk_overlap(self) -> int:
        return int(os.getenv("CHUNK_OVERLAP", "150"))

    @property
    def log_level(self) -> str:
        return os.getenv("LOG_LEVEL", "INFO").upper()

    @property
    def gemini_model(self) -> str:
        return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    @property
    def gemini_model_router_enabled(self) -> bool:
        """Enable deterministic model routing by task (default: True)."""
        return os.getenv("GEMINI_MODEL_ROUTER_ENABLED", "true").lower() in (
            "true", "1", "yes"
        )

    @property
    def gemini_model_complex(self) -> str:
        """Model for complex synthesis tasks (default: gemini-3-flash-preview)."""
        return os.getenv("GEMINI_MODEL_COMPLEX", "gemini-3-flash-preview")

    @property
    def gemini_model_cheap(self) -> str:
        """Model for cheap/auxiliary steps (default: gemini-3.1-flash-lite-preview)."""
        return os.getenv("GEMINI_MODEL_CHEAP", "gemini-3.1-flash-lite-preview")

    @property
    def gemini_model_qa_simple(self) -> str:
        """Model for simple QA responses (default: gemini-2.5-flash)."""
        return os.getenv("GEMINI_MODEL_QA_SIMPLE", "gemini-2.5-flash")

    @property
    def max_retries(self) -> int:
        return int(os.getenv("MAX_RETRIES", "2"))

    @property
    def min_citations(self) -> int:
        return int(os.getenv("MIN_CITATIONS", "2"))

    # â”€â”€ RAG retrieval tuning â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @property
    def min_relevance_score(self) -> float:
        return float(os.getenv("MIN_RELEVANCE_SCORE", "0.2"))

    @property
    def retrieval_mode(self) -> str:
        return os.getenv("RETRIEVAL_MODE", "mmr").lower()

    @property
    def mmr_fetch_k(self) -> int:
        default = str(self.top_k * 4)
        return int(os.getenv("MMR_FETCH_K", default))

    @property
    def mmr_lambda(self) -> float:
        return float(os.getenv("MMR_LAMBDA", "0.5"))

    @property
    def context_max_chars(self) -> int:
        return int(os.getenv("CONTEXT_MAX_CHARS", "1500"))

    # â”€â”€ Phase 2: Query rewriting â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @property
    def multi_query(self) -> bool:
        return os.getenv("MULTI_QUERY", "false").lower() in ("true", "1", "yes")

    @property
    def multi_query_n(self) -> int:
        return int(os.getenv("MULTI_QUERY_N", "3"))

    @property
    def multi_query_per_query_k(self) -> int:
        return int(os.getenv("MULTI_QUERY_PER_QUERY_K", str(self.top_k)))

    # â”€â”€ Phase 2: Reranking â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @property
    def reranker(self) -> str:
        """Reranker mode: 'none', 'local', or 'llm'."""
        return os.getenv("RERANKER", "none").lower()

    @property
    def rerank_top_n(self) -> int:
        return int(os.getenv("RERANK_TOP_N", str(self.top_k)))

    # â”€â”€ Phase 2: Hybrid search â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @property
    def bm25_dir(self) -> Path:
        return _path_env("BM25_DIR", "./data/bm25")

    @property
    def hybrid_k_lex(self) -> int:
        return int(os.getenv("HYBRID_K_LEX", str(self.top_k)))

    @property
    def hybrid_alpha(self) -> float:
        return float(os.getenv("HYBRID_ALPHA", "0.5"))

    # â”€â”€ Phase 2: Incremental ingest â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @property
    def ingest_incremental(self) -> bool:
        return os.getenv("INGEST_INCREMENTAL", "false").lower() in ("true", "1", "yes")

    # â”€â”€ Phase 3: Structured chunking â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @property
    def structured_chunking(self) -> bool:
        """When True, MD/TXT files are split by section headings (default: True)."""
        return os.getenv("STRUCTURED_CHUNKING", "true").lower() in ("true", "1", "yes")

    # â”€â”€ Phase 3: Semantic grounding verifier â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @property
    def grounded_verifier_mode(self) -> str:
        """Verifier mode: 'heuristic' (fast), 'llm' (LLM judge), or 'hybrid'.

        Default: 'heuristic' â€” safe to use without extra API calls.
        """
        return os.getenv("GROUNDED_VERIFIER_MODE", "heuristic").lower()

    @property
    def grounded_verifier_threshold(self) -> float:
        """Minimum heuristic score to consider a claim SUPPORTED (default: 0.65).

        Lower threshold = more lenient; higher = stricter.
        """
        return float(os.getenv("GROUNDED_VERIFIER_THRESHOLD", "0.65"))

    @property
    def min_support_rate(self) -> float:
        """Minimum CitationSupportRate before a repair pass is triggered (default: 0.5)."""
        return float(os.getenv("MIN_SUPPORT_RATE", "0.5"))

    @property
    def grounded_claims_mode(self) -> str:
        """Claim extraction mode: heuristic | llm | hybrid."""
        return os.getenv("GROUNDED_CLAIMS_MODE", "heuristic").lower()

    @property
    def grounding_repair_max_passes(self) -> int:
        """Maximum number of answer repair passes for low support rate (default: 1)."""
        return int(os.getenv("GROUNDING_REPAIR_MAX_PASSES", "1"))

    @property
    def grounding_retrieval_max_retries(self) -> int:
        """Maximum retrieval retries triggered by semantic grounding (default: 1)."""
        return int(os.getenv("GROUNDING_RETRIEVAL_MAX_RETRIES", "1"))

    @property
    def debug_grounding(self) -> bool:
        """Expose grounding details in API responses when enabled."""
        return os.getenv("DEBUG_GROUNDING", "false").lower() in ("true", "1", "yes")

    @property
    def semantic_grounding_enabled(self) -> bool:
        """Master switch for the semantic grounding verifier (default: True)."""
        return os.getenv("SEMANTIC_GROUNDING_ENABLED", "true").lower() in ("true", "1", "yes")

    # â”€â”€ Deep summary pipeline tuning â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @property
    def summary_group_size(self) -> int:
        """Target number of chunks per partial-summary group (default: 8).

        Larger values reduce LLM calls but produce coarser partial summaries.
        Smaller values give finer granularity but increase latency.
        Override with SUMMARY_GROUP_SIZE env var.
        """
        return int(os.getenv("SUMMARY_GROUP_SIZE", "8"))

    @property
    def summary_max_groups(self) -> int:
        """Hard cap on the number of groups in the deep summary pipeline (default: 6).

        Controls max partial-summary LLM calls, keeping latency predictable for
        very large documents. Override with SUMMARY_MAX_GROUPS env var.
        """
        return int(os.getenv("SUMMARY_MAX_GROUPS", "6"))

    @property
    def summary_section_threshold(self) -> float:
        """Min fraction of chunks with section metadata to use section-based
        grouping instead of a fixed sliding window (default: 0.70).

        Set lower (e.g. 0.5) to prefer section grouping on partially-structured docs.
        Override with SUMMARY_SECTION_THRESHOLD env var.
        """
        return float(os.getenv("SUMMARY_SECTION_THRESHOLD", "0.70"))

    @property
    def summary_max_sources(self) -> int:
        """Hard cap on source entries in the summary 'Fontes:' section (default: 12).

        Sources are grouped by (file, section) â€” this caps the total entries shown.
        Override with SUMMARY_MAX_SOURCES env var.
        """
        return int(os.getenv("SUMMARY_MAX_SOURCES", "12"))

    @property
    def summary_grounding_threshold(self) -> float:
        """Minimum token overlap to consider a summary block grounded (default: 0.20).

        Intentionally lenient: summary text is paraphrased, not verbatim.
        Lower = more permissive; raise (e.g. 0.35) for stricter validation.
        Override with SUMMARY_GROUNDING_THRESHOLD env var.
        """
        return float(os.getenv("SUMMARY_GROUNDING_THRESHOLD", "0.20"))

    @property
    def summary_grounding_repair(self) -> bool:
        """Enable LLM repair pass for weakly grounded blocks (default: False).

        When True, blocks below SUMMARY_GROUNDING_THRESHOLD receive an LLM
        rewrite restricted to the cited anchor texts. Adds 1 LLM call per
        weakly grounded block.
        Override with SUMMARY_GROUNDING_REPAIR env var.
        """
        return os.getenv("SUMMARY_GROUNDING_REPAIR", "false").lower() in (
            "true", "1", "yes"
        )

    @property
    def summary_grounding_max_repairs_per_pass(self) -> int:
        """Max weak-block grounding repairs per validation pass (default: 1).

        Limits how many weakly grounded blocks can trigger LLM rewrites in a
        single validate_summary_grounding() call, reducing tail latency on
        long summaries with many weak blocks.
        Override with SUMMARY_GROUNDING_MAX_REPAIRS_PER_PASS env var.
        """
        return int(os.getenv("SUMMARY_GROUNDING_MAX_REPAIRS_PER_PASS", "1"))

    @property
    def summary_grounding_repair_min_overlap(self) -> float:
        """Minimum overlap required to attempt grounding repair (default: 0.15).

        Repairs are expensive and can over-edit strong model outputs. With modern
        models, near-threshold blocks are usually acceptable paraphrases, so we
        only attempt repairs on clearly weak blocks below this overlap.
        Override with SUMMARY_GROUNDING_REPAIR_MIN_OVERLAP env var.
        """
        return float(os.getenv("SUMMARY_GROUNDING_REPAIR_MIN_OVERLAP", "0.15"))

    @property
    def summary_structure_min_chars(self) -> int:
        """Minimum non-citation text size per `##` section in deep summary (default: 160)."""
        return int(os.getenv("SUMMARY_STRUCTURE_MIN_CHARS", "160"))

    @property
    def summary_min_unique_sources(self) -> int:
        """Minimum number of distinct [Fonte N] references in deep summary (default: 5)."""
        return int(os.getenv("SUMMARY_MIN_UNIQUE_SOURCES", "5"))

    @property
    def summary_resynthesis_enabled(self) -> bool:
        """Enable one global re-synthesis pass when quality gates fail (default: False)."""
        return os.getenv("SUMMARY_RESYNTHESIS_ENABLED", "false").lower() in (
            "true", "1", "yes"
        )

    @property
    def summary_resynthesis_weak_block_ratio(self) -> float:
        """Trigger global re-synthesis when weak/cited grounding ratio >= this value (default: 0.50)."""
        return float(os.getenv("SUMMARY_RESYNTHESIS_WEAK_BLOCK_RATIO", "0.50"))

    @property
    def summary_resynthesis_max_weak_ratio_degradation(self) -> float:
        """Max allowed weak_ratio degradation when diversity improves (default: 0.05).

        If re-synthesis is triggered by citation diversity and candidate diversity
        improves, the candidate is only accepted when:
            candidate_weak_ratio <= current_weak_ratio + this_threshold
        """
        return float(os.getenv("SUMMARY_RESYNTHESIS_MAX_WEAK_RATIO_DEGRADATION", "0.05"))

    @property
    def summary_resynthesis_max_accepted_weak_ratio(self) -> float:
        """Absolute ceiling for weak_ratio on re-synthesis candidates (default: 0.35).

        A candidate is rejected regardless of quality/diversity gains when its
        weak_ratio exceeds this value. This prevents accepting summaries with
        objectively poor grounding even if they improve on other dimensions.
        """
        return float(os.getenv("SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO", "0.35"))

    @property
    def summary_grounding_threshold_noisy(self) -> float:
        """Grounding threshold used for noisy extraction artifacts (default: 0.12)."""
        return float(os.getenv("SUMMARY_GROUNDING_THRESHOLD_NOISY", "0.12"))

    @property
    def summary_grounding_noisy_chunk_ratio(self) -> float:
        """Noisy-document trigger: fraction of noisy chunks required (default: 0.25)."""
        return float(os.getenv("SUMMARY_GROUNDING_NOISY_CHUNK_RATIO", "0.25"))

    @property
    def summary_grounding_noisy_reduction_ratio(self) -> float:
        """Noisy-chunk trigger: min raw->clean reduction ratio (default: 0.03)."""
        return float(os.getenv("SUMMARY_GROUNDING_NOISY_REDUCTION_RATIO", "0.03"))

    @property
    def summary_resynthesis_require_structure(self) -> bool:
        """Require structure validation to pass before accepting re-synthesized candidate (default: True).

        When True, a re-synthesized candidate is only accepted if its structure
        is valid (correct heading count, required categories, no weak sections).
        Set False to fall back to the quality-signature-only gate.
        Override with SUMMARY_RESYNTHESIS_REQUIRE_STRUCTURE env var.
        """
        return os.getenv("SUMMARY_RESYNTHESIS_REQUIRE_STRUCTURE", "true").lower() in (
            "true", "1", "yes"
        )

    @property
    def summary_structure_fix_pass_enabled(self) -> bool:
        """Enable one LLM pass to fix structure when re-synthesis improves quality but fails structure (default: True).

        When True and a re-synthesized candidate improves grounding/diversity but
        has invalid structure, one extra LLM call is made to reorganize sections
        before the candidate is accepted or discarded.
        Override with SUMMARY_STRUCTURE_FIX_PASS_ENABLED env var.
        """
        return os.getenv("SUMMARY_STRUCTURE_FIX_PASS_ENABLED", "true").lower() in (
            "true", "1", "yes"
        )

    @property
    def summary_structure_fix_max_calls(self) -> int:
        """Maximum number of structure-fix LLM calls per re-synthesis attempt (default: 2)."""
        return int(os.getenv("SUMMARY_STRUCTURE_FIX_MAX_CALLS", "2"))

    @property
    def summary_outline_min_score(self) -> float:
        """Minimum outline topic coverage score for deep summary (default: 0.60).

        When the topic outline coverage score is below this threshold, a
        re-synthesis pass is triggered with explicit topic gap feedback.
        """
        return float(os.getenv("SUMMARY_OUTLINE_MIN_SCORE", "0.60"))

    # â”€â”€ Phase 3: Coverage gate â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @property
    def summary_coverage_gate_enabled(self) -> bool:
        """Enable content coverage gate for deep summary (default: True).

        When True, detected content signals (formulas, procedures, examples, concepts)
        from source chunks are compared against the final summary. Low coverage
        triggers a re-synthesis pass with explicit coverage feedback.
        Override with SUMMARY_COVERAGE_GATE_ENABLED env var.
        """
        return os.getenv("SUMMARY_COVERAGE_GATE_ENABLED", "true").lower() in (
            "true", "1", "yes"
        )

    @property
    def summary_coverage_profile(self) -> str:
        """Coverage profile selection mode for deep summary.

        Supported values:
        - ``auto`` (default): choose profile heuristically from document signals.
        - ``balanced`` | ``formula_heavy`` | ``procedural`` | ``narrative``.
        """
        return os.getenv("SUMMARY_COVERAGE_PROFILE", "auto").strip().lower()

    @property
    def summary_coverage_min_score_override(self) -> float | None:
        """Optional explicit override for profile min_score.

        Returns ``None`` when ``SUMMARY_COVERAGE_MIN_SCORE`` is not set in env.
        """
        raw = os.getenv("SUMMARY_COVERAGE_MIN_SCORE")
        if raw is None:
            return None
        return float(raw)

    @property
    def summary_coverage_min_score(self) -> float:
        """Minimum overall coverage score to pass the coverage gate (default: 0.50).

        Weighted mean of per-type coverage scores over active signal types.
        Score of 1.0 = full coverage; 0.0 = no coverage.
        Override with SUMMARY_COVERAGE_MIN_SCORE env var.
        """
        return float(os.getenv("SUMMARY_COVERAGE_MIN_SCORE", "0.50"))

    @property
    def summary_coverage_concept_min_hits(self) -> int:
        """Minimum number of concept-signal chunks to enable concept coverage check (default: 2).

        Prevents false positives when only one chunk has a definition-like pattern.
        Override with SUMMARY_COVERAGE_CONCEPT_MIN_HITS env var.
        """
        return int(os.getenv("SUMMARY_COVERAGE_CONCEPT_MIN_HITS", "2"))

    @property
    def summary_coverage_weight_formula(self) -> float:
        """Weight of formula/math signal in overall coverage score (default: 0.30).

        Override with SUMMARY_COVERAGE_WEIGHT_FORMULA env var.
        """
        return float(os.getenv("SUMMARY_COVERAGE_WEIGHT_FORMULA", "0.30"))

    @property
    def summary_coverage_weight_procedure(self) -> float:
        """Weight of procedure/algorithm signal in overall coverage score (default: 0.30).

        Override with SUMMARY_COVERAGE_WEIGHT_PROCEDURE env var.
        """
        return float(os.getenv("SUMMARY_COVERAGE_WEIGHT_PROCEDURE", "0.30"))

    @property
    def summary_coverage_weight_example(self) -> float:
        """Weight of example signal in overall coverage score (default: 0.20).

        Override with SUMMARY_COVERAGE_WEIGHT_EXAMPLE env var.
        """
        return float(os.getenv("SUMMARY_COVERAGE_WEIGHT_EXAMPLE", "0.20"))

    @property
    def summary_coverage_weight_concept(self) -> float:
        """Weight of concept/definition signal in overall coverage score (default: 0.20).

        Override with SUMMARY_COVERAGE_WEIGHT_CONCEPT env var.
        """
        return float(os.getenv("SUMMARY_COVERAGE_WEIGHT_CONCEPT", "0.20"))

    @property
    def summary_facet_min_hits(self) -> int:
        """Minimum chunk hits to mark a facet as required in deep-summary profile (default: 2)."""
        return int(os.getenv("SUMMARY_FACET_MIN_HITS", "2"))

    @property
    def summary_facet_gate_enabled(self) -> bool:
        """Enable facet-coverage gate based on detected document profile (default: True)."""
        return os.getenv("SUMMARY_FACET_GATE_ENABLED", "true").lower() in (
            "true", "1", "yes"
        )

    @property
    def summary_facet_min_score(self) -> float:
        """Minimum score for required facet coverage (default: 0.70)."""
        return float(os.getenv("SUMMARY_FACET_MIN_SCORE", "0.70"))

    @property
    def summary_notation_gate_enabled(self) -> bool:
        """Enable notation-fidelity gate for mathematical/cardinality notation (default: True)."""
        return os.getenv("SUMMARY_NOTATION_GATE_ENABLED", "true").lower() in (
            "true", "1", "yes"
        )

    @property
    def summary_notation_min_score(self) -> float:
        """Minimum notation-fidelity score for deep-summary acceptance (default: 0.75)."""
        return float(os.getenv("SUMMARY_NOTATION_MIN_SCORE", "0.75"))

    @property
    def summary_claim_gate_enabled(self) -> bool:
        """Enable critical-claim gate (procedures/formulas/validation) (default: True)."""
        return os.getenv("SUMMARY_CLAIM_GATE_ENABLED", "true").lower() in (
            "true", "1", "yes"
        )

    @property
    def summary_claim_min_score(self) -> float:
        """Minimum score for critical-claim cited coverage (default: 0.80)."""
        return float(os.getenv("SUMMARY_CLAIM_MIN_SCORE", "0.80"))

    @property
    def summary_rubric_gate_enabled(self) -> bool:
        """Enable composite quality-rubric gate for deep-summary acceptance (default: True)."""
        return os.getenv("SUMMARY_RUBRIC_GATE_ENABLED", "true").lower() in (
            "true", "1", "yes"
        )

    @property
    def summary_rubric_min_score(self) -> float:
        """Minimum composite rubric score for deep-summary acceptance (default: 0.72)."""
        return float(os.getenv("SUMMARY_RUBRIC_MIN_SCORE", "0.72"))

    @property
    def summary_notation_require_variable_legend(self) -> bool:
        """Require explicit variable legend when formula notation is present (default: True)."""
        return os.getenv("SUMMARY_NOTATION_REQUIRE_VARIABLE_LEGEND", "true").lower() in (
            "true", "1", "yes"
        )

    @property
    def summary_claim_local_repair_enabled(self) -> bool:
        """Enable deterministic local repair for missing critical claims (default: False)."""
        return os.getenv("SUMMARY_CLAIM_LOCAL_REPAIR_ENABLED", "false").lower() in (
            "true", "1", "yes"
        )

    @property
    def summary_final_gate_enabled(self) -> bool:
        """Enable strict fail-closed final quality gate (default: False)."""
        return os.getenv("SUMMARY_FINAL_GATE_ENABLED", "false").lower() in (
            "true", "1", "yes"
        )

    @property
    def summary_max_inference_density(self) -> float:
        """Maximum fraction of sentences with unsupported high-risk claims (default: 0.25).

        Inference density = (unsupported_high_risk_count + formula_downgraded_count)
                            / sentences_total.
        Values above this threshold trigger the de-overreach rewrite pass and,
        if not resolved, cause final.accepted=False.
        Override with SUMMARY_MAX_INFERENCE_DENSITY env var.
        """
        return float(os.getenv("SUMMARY_MAX_INFERENCE_DENSITY", "0.25"))

    @property
    def summary_formula_mode(self) -> str:
        """Formula-claim verification mode: 'conservative' (default) or 'permissive'.

        In 'conservative' mode, formula/mathematical claims in the summary must be
        backed by at least one cited anchor that contains actual math content
        (Greek letters, operators, algebraic notation). Claims without such backing
        are downgraded to a conceptual description and counted toward inference density.
        Override with SUMMARY_FORMULA_MODE env var.
        """
        return os.getenv("SUMMARY_FORMULA_MODE", "conservative").strip().lower()

    @property
    def summary_deoverreach_max_context_sources(self) -> int:
        """Max citation anchors injected into de-overreach prompt context (default: 6)."""
        return int(os.getenv("SUMMARY_DEOVERREACH_MAX_CONTEXT_SOURCES", "6"))

    @property
    def summary_deoverreach_context_chars(self) -> int:
        """Max chars per anchor snippet in de-overreach context (default: 700)."""
        return int(os.getenv("SUMMARY_DEOVERREACH_CONTEXT_CHARS", "700"))

    @property
    def summary_deoverreach_max_prompt_chars(self) -> int:
        """Skip de-overreach pass when prompt exceeds this size (default: 18000)."""
        return int(os.getenv("SUMMARY_DEOVERREACH_MAX_PROMPT_CHARS", "18000"))

    @property
    def summary_latency_budget_seconds(self) -> float:
        """Soft latency budget for optional deep-summary passes (default: 300s)."""
        return float(os.getenv("SUMMARY_LATENCY_BUDGET_SECONDS", "300"))

    # â”€â”€ Phase 3: Eval harness â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @property
    def eval_suites_dir(self) -> Path:
        return _path_env("EVAL_SUITES_DIR", "./eval/suites")

    @property
    def eval_output_dir(self) -> Path:
        return _path_env("EVAL_OUTPUT_DIR", "./artifacts")

    # â”€â”€ Auth / banco de dados â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @property
    def database_url(self) -> str:
        default = f"sqlite:///{(_project_root / 'data' / 'app.db').as_posix()}"
        return os.getenv("DATABASE_URL", default)

    @property
    def jwt_secret_key(self) -> str:
        key = os.getenv("JWT_SECRET_KEY", "")
        if not key:
            raise EnvironmentError(
                "JWT_SECRET_KEY nÃ£o configurado. Defina no .env antes de iniciar o servidor."
            )
        return key

    @property
    def jwt_algorithm(self) -> str:
        return os.getenv("JWT_ALGORITHM", "HS256")

    @property
    def jwt_expires_minutes(self) -> int:
        return int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "60"))

    @property
    def ingest_allowed_dirs(self) -> list[Path]:
        """DiretÃ³rios permitidos para ingest por path (evita leitura arbitrÃ¡ria de disco)."""
        raw = os.getenv("INGEST_ALLOWED_DIRS", "")
        if raw:
            return [Path(d.strip()).resolve() for d in raw.split(",") if d.strip()]
        return [self.docs_dir.resolve()]

    # â”€â”€ Deep summary execution profiles â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @property
    def summary_deep_profile(self) -> str:
        """Execution profile for the deep summary pipeline.

        Values:
          - ``fast``      â€” caminho crÃ­tico sem passes caros (sem deoverreach,
                            resynthesis ou backfill extra). Apenas validaÃ§Ãµes
                            essenciais. Menor latÃªncia.
          - ``balanced``  â€” perfil recomendado para produÃ§Ã£o: pipeline completo
                            com gates de qualidade ativos, sem fail-closed
                            estrito por padrÃ£o.
          - ``model_first`` â€” caminho ultrassimples para modelos modernos:
                            evita passes corretivos em cascata e prioriza
                            sÃ­ntese direta com validaÃ§Ãµes bÃ¡sicas.
          - ``model_first_plus`` â€” igual ao model_first, mas habilita
                            apenas o passe de de-overreach.
          - ``model_first_plus_max`` â€” igual ao model_first_plus, com
                            micro-backfill de tÃ³picos obrigatÃ³rios.
          - ``strict``    â€” 1 passe corretivo mÃ¡ximo + fail-closed real: se
                            diagnostics.final.accepted=False, retorna erro HTTP 422.

        Override with SUMMARY_DEEP_PROFILE env var.
        """
        val = os.getenv("SUMMARY_DEEP_PROFILE", "balanced").strip().lower()
        if val not in (
            "fast",
            "balanced",
            "model_first",
            "model_first_plus",
            "model_first_plus_max",
            "strict",
        ):
            return "balanced"
        return val

    @property
    def summary_max_corrective_passes(self) -> int:
        """OrÃ§amento global de passes corretivos por run de deep summary (default: 1).

        Conta deoverreach, resynthesis e backfill como passes distintos.
        Quando o orÃ§amento for atingido, nenhum passe corretivo adicional Ã© iniciado.
        Override with SUMMARY_MAX_CORRECTIVE_PASSES env var.
        """
        return max(0, int(os.getenv("SUMMARY_MAX_CORRECTIVE_PASSES", "1")))

    @property
    def summary_style_polish_enabled(self) -> bool:
        """Habilita passo de polish de estilo (polish_deep_summary_style) (default: False).

        Quando False, o passo de polish Ã© ignorado.
        Em perfil ``fast``, sempre desabilitado independentemente deste valor.
        Override with SUMMARY_STYLE_POLISH_ENABLED env var.
        """
        return os.getenv("SUMMARY_STYLE_POLISH_ENABLED", "false").lower() in (
            "true", "1", "yes"
        )

    @property
    def summary_fail_closed_strict(self) -> bool:
        """Em perfil ``strict``, retorna HTTP 422 quando accepted=False (default: True).

        Quando True e perfil=strict: se diagnostics.final.accepted=False, a API
        retorna HTTP 422 com detalhe dos blocking_reasons em vez de entregar o resumo.
        Override with SUMMARY_FAIL_CLOSED_STRICT env var.
        """
        return os.getenv("SUMMARY_FAIL_CLOSED_STRICT", "true").lower() in (
            "true", "1", "yes"
        )

    # â”€â”€ Micro-backfill (tÃ³pico direcionado) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @property
    def summary_micro_backfill_enabled(self) -> bool:
        """Habilita micro-backfill direcionado por tÃ³pico (default: True).

        Quando True, substitui o backfill global por chamadas LLM por tÃ³pico,
        gerando apenas 1 parÃ¡grafo curto por tÃ³pico faltante em vez de reescrever
        o resumo inteiro.
        Override with SUMMARY_MICRO_BACKFILL_ENABLED env var.
        """
        return os.getenv("SUMMARY_MICRO_BACKFILL_ENABLED", "true").lower() in (
            "true", "1", "yes"
        )

    @property
    def summary_micro_backfill_max_topics(self) -> int:
        """MÃ¡ximo de tÃ³picos processados por chamada de micro-backfill (default: 3).

        Limita o nÃºmero de tÃ³picos que recebem um parÃ¡grafo de complemento.
        TÃ³picos excedentes sÃ£o registrados nos diagnÃ³sticos mas nÃ£o processados.
        Override with SUMMARY_MICRO_BACKFILL_MAX_TOPICS env var.
        """
        return max(1, int(os.getenv("SUMMARY_MICRO_BACKFILL_MAX_TOPICS", "3")))

    @property
    def summary_micro_backfill_paragraph_max_chars(self) -> int:
        """Limite mÃ¡ximo de caracteres por parÃ¡grafo gerado pelo micro-backfill (default: 900).

        O parÃ¡grafo gerado pelo LLM Ã© truncado se exceder este limite antes da
        validaÃ§Ã£o. Deve equivaler a ~60-120 palavras em PT-BR.
        Override with SUMMARY_MICRO_BACKFILL_PARAGRAPH_MAX_CHARS env var.
        """
        return max(200, int(os.getenv("SUMMARY_MICRO_BACKFILL_PARAGRAPH_MAX_CHARS", "900")))

    @property
    def summary_require_non_low_info_for_high_risk(self) -> bool:
        """Exige ao menos 1 fonte nÃ£o-low-info para claims high-risk (default: True).

        Quando True, claims tÃ©cnicos (formula, quantitative, taxonomy_comparison,
        technical_assertion) sÃ£o marcados como unsupported quando TODAS as fontes
        citadas sÃ£o low-info (sumÃ¡rio, Ã­ndice, conteÃºdo, etc.).
        Override with SUMMARY_REQUIRE_NON_LOW_INFO_FOR_HIGH_RISK env var.
        """
        return os.getenv("SUMMARY_REQUIRE_NON_LOW_INFO_FOR_HIGH_RISK", "true").lower() in (
            "true", "1", "yes"
        )

    @property
    def summary_strict_reserve_pass_for_must_cover(self) -> bool:
        """Reserva 1 passe corretivo para cobertura obrigatÃ³ria no perfil strict (default: True).

        Quando True e profile=strict, se houver `must_cover_topics` ainda faltando
        e restar apenas 1 passe corretivo, o scheduler prioriza cobertura de tÃ³picos
        (micro-backfill) e impede que de-overreach/resynthesis consumam esse Ãºltimo passe.
        Override with SUMMARY_STRICT_RESERVE_PASS_FOR_MUST_COVER env var.
        """
        return os.getenv(
            "SUMMARY_STRICT_RESERVE_PASS_FOR_MUST_COVER",
            "true",
        ).lower() in ("true", "1", "yes")

    @property
    def summary_backfill_before_deoverreach(self) -> bool:
        """Executa micro-backfill antes de de-overreach/resynthesis (default: True).

        Quando True e hÃ¡ missing must-cover topics, o micro-backfill Ã© executado
        ANTES de de-overreach e resynthesis no perfil strict.
        Isso reduz casos de final_accepted=False por missing_topics quando
        max_corrective_passes=1, pois o Ãºnico passe disponÃ­vel vai para cobertura.

        Quando False, mantÃ©m a ordem legada: deoverreach â†’ resynthesis â†’ micro-backfill.
        NÃ£o tem efeito no perfil fast (passes corretivos sempre desabilitados).
        Override with SUMMARY_BACKFILL_BEFORE_DEOVERREACH env var.
        """
        return os.getenv("SUMMARY_BACKFILL_BEFORE_DEOVERREACH", "true").lower() in (
            "true", "1", "yes"
        )


# Singleton instance used throughout the package
config = Config()

