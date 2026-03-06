"""Configuration management — reads all settings from environment variables.

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
        return os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    @property
    def max_retries(self) -> int:
        return int(os.getenv("MAX_RETRIES", "2"))

    @property
    def min_citations(self) -> int:
        return int(os.getenv("MIN_CITATIONS", "2"))

    # ── RAG retrieval tuning ──────────────────────────────────────────────────

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

    # ── Phase 2: Query rewriting ───────────────────────────────────────────────

    @property
    def multi_query(self) -> bool:
        return os.getenv("MULTI_QUERY", "false").lower() in ("true", "1", "yes")

    @property
    def multi_query_n(self) -> int:
        return int(os.getenv("MULTI_QUERY_N", "3"))

    @property
    def multi_query_per_query_k(self) -> int:
        return int(os.getenv("MULTI_QUERY_PER_QUERY_K", str(self.top_k)))

    # ── Phase 2: Reranking ─────────────────────────────────────────────────────

    @property
    def reranker(self) -> str:
        """Reranker mode: 'none', 'local', or 'llm'."""
        return os.getenv("RERANKER", "none").lower()

    @property
    def rerank_top_n(self) -> int:
        return int(os.getenv("RERANK_TOP_N", str(self.top_k)))

    # ── Phase 2: Hybrid search ─────────────────────────────────────────────────

    @property
    def bm25_dir(self) -> Path:
        return _path_env("BM25_DIR", "./data/bm25")

    @property
    def hybrid_k_lex(self) -> int:
        return int(os.getenv("HYBRID_K_LEX", str(self.top_k)))

    @property
    def hybrid_alpha(self) -> float:
        return float(os.getenv("HYBRID_ALPHA", "0.5"))

    # ── Phase 2: Incremental ingest ────────────────────────────────────────────

    @property
    def ingest_incremental(self) -> bool:
        return os.getenv("INGEST_INCREMENTAL", "false").lower() in ("true", "1", "yes")

    # ── Phase 3: Structured chunking ──────────────────────────────────────────

    @property
    def structured_chunking(self) -> bool:
        """When True, MD/TXT files are split by section headings (default: True)."""
        return os.getenv("STRUCTURED_CHUNKING", "true").lower() in ("true", "1", "yes")

    # ── Phase 3: Semantic grounding verifier ──────────────────────────────────

    @property
    def grounded_verifier_mode(self) -> str:
        """Verifier mode: 'heuristic' (fast), 'llm' (LLM judge), or 'hybrid'.

        Default: 'heuristic' — safe to use without extra API calls.
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

    # ── Phase 3: Eval harness ─────────────────────────────────────────────────

    @property
    def eval_suites_dir(self) -> Path:
        return _path_env("EVAL_SUITES_DIR", "./eval/suites")

    @property
    def eval_output_dir(self) -> Path:
        return _path_env("EVAL_OUTPUT_DIR", "./artifacts")

    # ── Auth / banco de dados ──────────────────────────────────────────────────

    @property
    def database_url(self) -> str:
        default = f"sqlite:///{(_project_root / 'data' / 'app.db').as_posix()}"
        return os.getenv("DATABASE_URL", default)

    @property
    def jwt_secret_key(self) -> str:
        key = os.getenv("JWT_SECRET_KEY", "")
        if not key:
            raise EnvironmentError(
                "JWT_SECRET_KEY não configurado. Defina no .env antes de iniciar o servidor."
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
        """Diretórios permitidos para ingest por path (evita leitura arbitrária de disco)."""
        raw = os.getenv("INGEST_ALLOWED_DIRS", "")
        if raw:
            return [Path(d.strip()).resolve() for d in raw.split(",") if d.strip()]
        return [self.docs_dir.resolve()]


# Singleton instance used throughout the package
config = Config()
