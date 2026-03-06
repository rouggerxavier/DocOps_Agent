# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Preferências de idioma
Responda SEMPRE em português brasileiro.

- Faça perguntas de follow-up em português.
- Use termos técnicos quando necessário, mas explique rapidamente.
- Se eu escrever em inglês, ainda assim responda em PT-BR, a menos que eu peça o contrário.

## Commands
All Python commands run from `docops-agent/` with the venv active.

```bash
# Activate venv
source .venv/Scripts/activate          # Git Bash
.venv\Scripts\Activate.ps1             # PowerShell

# Install deps
pip install -r docops-agent/requirements.txt
pip install -e "docops-agent/[dev]"    # includes pytest

# Run tests
cd docops-agent && pytest
pytest tests/test_api.py               # single file
pytest tests/test_api.py::test_name    # single test

# CLI
cd docops-agent
python -m docops ingest --path ./docs
python -m docops chat
python -m docops list-docs
python -m docops summarize --doc <name>
python -m docops compare --doc1 <name> --doc2 <name>
python -m docops artifact --type study_plan --topic <name>

# API server
uvicorn docops.api.app:app --reload

# Frontend
cd docops-agent/web && npm install
npm run dev     # dev server
npm run build   # production build
npm run lint
```

## Architecture

### Request Flow

```
User query
  → CLI (typer/rich) or FastAPI
  → LangGraph graph (graph/graph.py)
      ├── classify_intent  — detects qa / summary / comparison / artifact
      ├── retrieve         — tool_search_docs → Chroma + BM25 hybrid + reranking
      ├── synthesize       — Gemini LLM + intent-specific prompt
      ├── verify_grounding — citation check + phantom citation detection + factuality
      ├── retry_retrieve   — widens top_k and retries if grounding fails
      └── finalize         — assembles response with "Fontes:" section
```

### Key Modules

- **`graph/state.py`** — `AgentState` TypedDict: the single shared state object passed between all LangGraph nodes.
- **`graph/nodes.py`** — Each LangGraph node is a function that reads/writes `AgentState`. Nodes call tools from `tools/doc_tools.py` and RAG utilities.
- **`config.py`** — Single source of truth for all env vars. All modules import `settings` from here; never read env vars directly elsewhere.
- **`ingestion/indexer.py`** — `get_vectorstore()` returns a singleton Chroma client. `index_chunks()` uses SHA-256 stable IDs to support incremental indexing (`INGEST_INCREMENTAL=true`).
- **`rag/retriever.py`** — Orchestrates multi-query rewriting, hybrid retrieval (Chroma MMR/similarity + BM25 via RRF), score thresholding, and reranking in one call.
- **`rag/hybrid.py`** — BM25 index backed by a persistent pickle in `BM25_DIR`. Must be rebuilt when documents change.
- **`rag/verifier.py`** — `verify_grounding()` checks that every `[Fonte N]` citation in the synthesis maps to a real retrieved chunk and flags hallucinated references.
- **`rag/citations.py`** — Builds the numbered context block sent to the LLM and the "Fontes:" section in the final answer.
- **`tools/doc_tools.py`** — LangChain-compatible tools exposed to the LangGraph agent: `tool_search_docs`, `tool_read_chunk`, `tool_write_artifact`, `tool_list_docs`.

### Retrieval Modes (`RETRIEVAL_MODE`)

- `similarity` — plain cosine search in Chroma
- `mmr` — Maximal Marginal Relevance (diversity-aware), default
- `hybrid` — MMR + BM25 merged via Reciprocal Rank Fusion

### Frontend

React 19 + TypeScript SPA in `docops-agent/web/`. Communicates with the FastAPI backend. Uses TanStack Query for data fetching, Radix UI for components, and react-markdown to render LLM responses.

## Environment

Copy `docops-agent/.env.example` → `docops-agent/.env`. Required: `GEMINI_API_KEY`.

The CLI and tests use relative paths from `docops-agent/` (e.g. `./data/chroma`, `./docs`), so always run Python commands from inside that directory.

ChromaDB is pinned to `<0.6.0` and requires Python 3.11 or 3.12 (not 3.13+).
