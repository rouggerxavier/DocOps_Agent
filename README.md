# DocOps Agent

> **Document Operations Agent** â€” RAG + LangGraph + Google Gemini + ChromaDB

Agente conversacional que opera sobre documentos tÃ©cnicos usando Retrieval-Augmented Generation (RAG). Indexa PDFs, Markdown e TXT em um ChromaDB persistente e responde perguntas com citaÃ§Ãµes rastreÃ¡veis, verificaÃ§Ã£o de fundamentaÃ§Ã£o semÃ¢ntica e suporte a mÃºltiplos intents (QA, resumo, comparaÃ§Ã£o, plano de estudos, artefatos).

## Multi-tenancy por usuário (atualizado em 2026-03-06)

Esta versão implementa isolamento forte por usuário em toda a stack. Este bloco substitui referências antigas no README que ainda mencionam recursos globais.

Princípios aplicados:
- Banco SQL único com ownership explícito (`user_id`) nas entidades de domínio.
- Chroma isolado por usuário com collection dedicada: `docops_user_<user_id>`.
- BM25 isolado por usuário em diretório dedicado.
- Uploads e artifacts segregados por usuário no filesystem.
- Validação de ownership no backend (rotas e serviços); frontend não define autorização.

Fonte de verdade de ownership:
- `DocumentRecord` e `ArtifactRecord` no SQL (não o filesystem e não o Chroma).
- Chroma/BM25 são índices de busca, não cadastro/autorização.

Layout de storage por usuário:
```text
uploads/user_<id>/
artifacts/user_<id>/
data/bm25/user_<id>/bm25_index.pkl
data/bm25/user_<id>/bm25_index.json
Chroma collection: docops_user_<id>
```

Decisões arquiteturais:
- Collection por usuário no Chroma foi escolhida para reduzir risco de vazamento por filtro ausente.
- SQL é a fonte de verdade para ownership, listagem de docs e listagem de artifacts.
- `file_name` sozinho não é identidade segura; resolução usa ownership + `doc_id`.

Compatibilidade/legado:
- Conteúdo legado global em `data/chroma`, `data/bm25`, `artifacts` e `docs` pode ser reindexado no novo modelo.
- Não há migração automática de índices globais antigos para evitar migração implícita insegura.

Impacto em produção:
- Endpoints continuam os mesmos (`/api/ingest`, `/api/docs`, `/api/chat`, `/api/summarize`, `/api/compare`, `/api/artifact`, `/api/artifacts`).
- O isolamento agora é por conta autenticada (`current_user`) em todas as operações.
- A transição para PostgreSQL no futuro mantém o mesmo desenho de ownership (FK por `user_id`).

---

## Ãndice

1. [PrÃ©-requisitos](#prÃ©-requisitos)
2. [InstalaÃ§Ã£o](#instalaÃ§Ã£o)
3. [ConfiguraÃ§Ã£o (.env)](#configuraÃ§Ã£o-env)
4. [Como rodar](#como-rodar)
5. [Arquitetura Geral](#arquitetura-geral)
6. [Stack TecnolÃ³gica](#stack-tecnolÃ³gica)
7. [Estrutura de Pastas](#estrutura-de-pastas)
8. [MÃ³dulos â€” DescriÃ§Ã£o Detalhada](#mÃ³dulos--descriÃ§Ã£o-detalhada)
9. [LangGraph Pipeline](#langgraph-pipeline)
10. [AgentState â€” Estado Compartilhado](#agentstate--estado-compartilhado)
11. [Ingestion Pipeline](#ingestion-pipeline)
12. [RAG â€” Retrieval-Augmented Generation](#rag--retrieval-augmented-generation)
13. [Grounding Verifier SemÃ¢ntico](#grounding-verifier-semÃ¢ntico)
14. [API REST (FastAPI)](#api-rest-fastapi)
15. [AutenticaÃ§Ã£o (JWT + SQLite)](#autenticaÃ§Ã£o-jwt--sqlite)
16. [Frontend (React + Vite)](#frontend-react--vite)
17. [CLI â€” Comandos](#cli--comandos)
18. [Eval Harness](#eval-harness)
19. [Testes](#testes)
20. [DependÃªncias](#dependÃªncias)

---

## PrÃ©-requisitos

| Requisito | VersÃ£o |
|---|---|
| Python | **3.11 ou 3.12** (ChromaDB < 0.6 nÃ£o suporta 3.13+) |
| Node.js | 18+ (para o frontend React) |
| Google Gemini API Key | [ai.google.dev](https://ai.google.dev/) |

> **Nota Python 3.14+:** Se o seu sistema tiver Python 3.14 instalado, crie o venv explicitamente:
> ```bash
> py -3.11 -m venv .venv
> ```

---

## InstalaÃ§Ã£oFFJYFHHHFHFGGDJSGSD
```bash
# 1. Entre na pasta do projeto
cd DocOps_Agent

# 2. Crie e ative o ambiente virtual (Python 3.11 ou 3.12)
py -3.11 -m venv .venv
.venv\Scripts\activate          # Windows PowerShell

# 3. Instale as dependÃªncias Python
pip install -r requirements.txt

# 4. Configure as variÃ¡veis de ambiente
copy .env.example .env
# Edite .env e preencha GEMINI_API_KEY e JWT_SECRET_KEY

# 5. Instale dependÃªncias do frontend
cd web
npm install
cd ..
```

---

## ConfiguraÃ§Ã£o (.env)

O arquivo `.env` fica na raiz `DocOps_Agent/`. Todas as configuraÃ§Ãµes sÃ£o lidas pelo singleton `config` em `docops/config.py` â€” **nunca** leia env vars diretamente no cÃ³digo, sempre use `config`.

### VariÃ¡veis obrigatÃ³rias

| VariÃ¡vel | DescriÃ§Ã£o |
|---|---|
| `GEMINI_API_KEY` | Chave da API Google Gemini |
| `JWT_SECRET_KEY` | Segredo para assinar tokens JWT â€” gere com: `python -c "import secrets; print(secrets.token_hex(32))"` |

### Caminhos

| VariÃ¡vel | PadrÃ£o | DescriÃ§Ã£o |
|---|---|---|
| `CHROMA_DIR` | `./data/chroma` | DiretÃ³rio de persistÃªncia do ChromaDB |
| `DOCS_DIR` | `./docs` | Base de ingest por path local permitido (`INGEST_ALLOWED_DIRS`) |
| `UPLOADS_DIR` | `./uploads` | Uploads recebidos pela API, segregados em `uploads/user_<id>/` |
| `ARTIFACTS_DIR` | `./artifacts` | Base de artifacts; API grava emC `artifacts/user_<id>/` |
| `BM25_DIR` | `./data/bm25` | Base dos índices BM25 por usuário (`data/bm25/user_<id>/`) |

### Chunking

| VariÃ¡vel | PadrÃ£o | DescriÃ§Ã£o |
|---|---|---|
| `CHUNK_SIZE` | `900` | Tamanho de cada chunk em caracteres |
| `CHUNK_OVERLAP` | `150` | SobreposiÃ§Ã£o entre chunks |
| `STRUCTURED_CHUNKING` | `true` | Chunking por seÃ§Ã£o para MD/TXT (vs. tamanho fixo) |
| `INGEST_INCREMENTAL` | `false` | Pular re-indexaÃ§Ã£o de chunks inalterados (SHA-256 IDs) |

### Retrieval

| VariÃ¡vel | PadrÃ£o | DescriÃ§Ã£o |
|---|---|---|
| `RETRIEVAL_MODE` | `mmr` | Modo: `mmr`, `similarity`, `hybrid` (BM25 + vector) |
| `TOP_K` | `6` | NÃºmero de chunks recuperados por query |
| `MIN_RELEVANCE_SCORE` | `0.2` | Score mÃ­nimo â€” chunks abaixo sÃ£o descartados |
| `MMR_FETCH_K` | `top_k Ã— 4` | Candidatos buscados antes do re-ranking MMR |
| `MMR_LAMBDA` | `0.5` | BalanÃ§o MMR: 0 = diversidade mÃ¡x, 1 = relevÃ¢ncia mÃ¡x |
| `CONTEXT_MAX_CHARS` | `1500` | MÃ¡x de chars do chunk no contexto do LLM (0 = sem limite) |
| `HYBRID_K_LEX` | `top_k` | NÃºmero de resultados BM25 no modo hybrid |
| `HYBRID_ALPHA` | `0.5` | Peso reservado (RRF usado por padrÃ£o) |

### Multi-query

| VariÃ¡vel | PadrÃ£o | DescriÃ§Ã£o |
|---|---|---|
| `MULTI_QUERY` | `false` | Reescreve a query em N variaÃ§Ãµes para maior recall |
| `MULTI_QUERY_N` | `3` | NÃºmero de variaÃ§Ãµes de query |
| `MULTI_QUERY_PER_QUERY_K` | `top_k` | top_k por variaÃ§Ã£o individual |

### Reranking

| VariÃ¡vel | PadrÃ£o | DescriÃ§Ã£o |
|---|---|---|
| `RERANKER` | `none` | Modo: `none`, `local` (bag-of-words), `llm` (Gemini) |
| `RERANK_TOP_N` | `top_k` | Documentos a manter apÃ³s reranking |

### Grounding semÃ¢ntico

| VariÃ¡vel | PadrÃ£o | DescriÃ§Ã£o |
|---|---|---|
| `SEMANTIC_GROUNDING_ENABLED` | `true` | Master switch do verificador semÃ¢ntico |
| `GROUNDED_VERIFIER_MODE` | `heuristic` | Modo: `heuristic`, `llm`, `hybrid` |
| `GROUNDED_VERIFIER_THRESHOLD` | `0.65` | Score mÃ­nimo para considerar claim como SUPPORTED |
| `GROUNDED_CLAIMS_MODE` | `heuristic` | ExtraÃ§Ã£o de claims: `heuristic`, `llm`, `hybrid` |
| `MIN_SUPPORT_RATE` | `0.5` | Taxa mÃ­nima de suporte antes de repair/retry |
| `GROUNDING_REPAIR_MAX_PASSES` | `1` | MÃ¡ximo de passes de repair semÃ¢ntico |
| `GROUNDING_RETRIEVAL_MAX_RETRIES` | `1` | Retries de retrieval disparados pelo grounding |
| `DEBUG_GROUNDING` | `false` | ExpÃµe payload de grounding em API/CLI |

### Auth e Banco

| VariÃ¡vel | PadrÃ£o | DescriÃ§Ã£o |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/app.db` | URL de conexÃ£o SQLAlchemy |
| `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` | `60` | Validade do access token em minutos |
| `JWT_ALGORITHM` | `HS256` | Algoritmo JWT |
| `INGEST_ALLOWED_DIRS` | `DOCS_DIR` | DiretÃ³rios permitidos para ingest por path (seguranÃ§a) |

### CORS e LLM

| VariÃ¡vel | PadrÃ£o | DescriÃ§Ã£o |
|---|---|---|
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | Origins permitidas pelo CORS |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Modelo Gemini para sÃ­ntese e classificaÃ§Ã£o |
| `LOG_LEVEL` | `INFO` | NÃ­vel de log: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `MAX_RETRIES` | `2` | MÃ¡ximo de retries no verify_grounding (citaÃ§Ãµes) |
| `MIN_CITATIONS` | `2` | MÃ­nimo de citaÃ§Ãµes `[Fonte N]` exigidas na resposta |

### Eval

| VariÃ¡vel | PadrÃ£o | DescriÃ§Ã£o |
|---|---|---|
| `EVAL_SUITES_DIR` | `./eval/suites` | DiretÃ³rio com suites YAML de avaliaÃ§Ã£o |
| `EVAL_OUTPUT_DIR` | `./artifacts` | DiretÃ³rio de saÃ­da dos relatÃ³rios de eval |

---

## Como rodar

### Backend (FastAPI + Uvicorn)

```bash
# Na pasta DocOps_Agent/, com .venv ativo
python -m uvicorn docops.api.app:app --reload
```

- Backend: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/api/docs-ui`
- Health check: `http://localhost:8000/api/health`

Alternativa via CLI:

```bash
python -m docops serve --reload
```

### Frontend (React + Vite)

```bash
# Em outro terminal, sem precisar do venv
cd DocOps_Agent/web
npm run dev
```

- Frontend: `http://localhost:5173` (ou prÃ³xima porta disponÃ­vel, ex: `5174`)
- Se a porta for diferente de `5173`, adicione ao `.env`: `CORS_ORIGINS=http://localhost:5174`

### Docker (backend + frontend)

Arquivos adicionados:
- `Dockerfile.backend`
- `Dockerfile.frontend`
- `docker-compose.yml`
- `docker/nginx.conf`

Passo a passo:

```bash
# Na raiz DocOps_Agent/
copy .env.example .env
# Edite .env e preencha GEMINI_API_KEY e JWT_SECRET_KEY

docker compose up --build
```

Endpoints:
- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/api/docs-ui`

PersistÃªncia em volume bind local:
- `./data` -> banco SQLite, Chroma e BM25
- `./docs` -> documentos para ingest por path
- `./uploads` -> uploads via API
- `./artifacts` -> artefatos gerados

ObservaÃ§Ãµes:
- O frontend em `http://localhost:5173` faz proxy de `/api/*` para o container `backend`.
- Para ingest por path dentro do container, use `POST /api/ingest` com caminhos em `/app/docs/...`.
- Para encerrar os containers: `docker compose down`
- Para rebuild apÃ³s alterar dependÃªncias: `docker compose up --build`

---

## Arquitetura Geral

```
UsuÃ¡rio (Browser)
      |
      v
React + Vite (frontend â€” web/)
      |  HTTP/REST com Bearer token
      v
FastAPI (docops/api/) â€” autenticaÃ§Ã£o JWT
      |
      v
LangGraph Agent (docops/graph/)
      |
      +-- classify_intent    --> detecta intent (qa/summary/comparison/...)
      +-- retrieve           --> tool_search_docs --> Chroma MMR/similarity/hybrid
      +-- synthesize         --> Gemini LLM + prompt especializado por intent
      +-- verify_grounding   --> verifica citaÃ§Ãµes + grounding semÃ¢ntico claim->evidence
      +-- retry_retrieve     --> repete com top_k maior se necessÃ¡rio
      +-- finalize           --> monta resposta + seÃ§Ã£o "Fontes:"
      |
      +-- ChromaDB (data/chroma/)     -- vetores + metadados dos chunks
      +-- BM25 Index (data/bm25/)     -- Ã­ndice lexical para hybrid search
      +-- SQLite (data/app.db)        -- usuÃ¡rios + autenticaÃ§Ã£o
```

---

## Stack TecnolÃ³gica

### Backend Python

| Camada | Tecnologia |
|---|---|
| LLM | Google Gemini via `langchain-google-genai` (`gemini-2.5-flash` por padrÃ£o) |
| Embeddings | `models/gemini-embedding-001` (Google GenAI, hardcoded) |
| OrquestraÃ§Ã£o do agente | LangGraph (`StateGraph`) |
| Vector store | ChromaDB persistente (`langchain-chroma`) |
| BM25 | `rank-bm25` (BM25Okapi) |
| Framework RAG | LangChain (`langchain`, `langchain-text-splitters`) |
| API Web | FastAPI + Uvicorn |
| AutenticaÃ§Ã£o | JWT (`PyJWT`) + bcrypt |
| Banco de dados | SQLAlchemy 2.x + SQLite (produÃ§Ã£o: PostgreSQL) |
| CLI | Typer + Rich |
| PDF loading | pypdf |
| ConfiguraÃ§Ã£o | python-dotenv |
| ValidaÃ§Ã£o | Pydantic v2 |
| YAML (eval) | pyyaml |

### Frontend

| Camada | Tecnologia |
|---|---|
| Framework | React 18 |
| Build tool | Vite 7 |
| Linguagem | TypeScript |

---

## Estrutura de Pastas

```
DocOps_Agent/                        <- raiz do projeto (workspace VSCode)
|-- .env                             <- variÃ¡veis de ambiente (nÃ£o comitar)
|-- .env.example                     <- template de variÃ¡veis
|-- .venv/                           <- ambiente virtual Python (nÃ£o comitar)
|-- pyproject.toml                   <- dependÃªncias e metadados do projeto
|-- requirements.txt                 <- dependÃªncias pinadas
|-- README.md                        <- este arquivo
|
|-- docops/                          <- pacote Python principal
|   |-- __init__.py
|   |-- __main__.py                  <- entrypoint: python -m docops
|   |-- cli.py                       <- comandos CLI (typer): ingest, chat, serve, eval, ...
|   |-- config.py                    <- singleton Config â€” lÃª todas as env vars
|   |-- logging.py                   <- logger configurÃ¡vel via LOG_LEVEL
|   |
|   |-- graph/                       <- LangGraph agent
|   |   |-- graph.py                 <- build_graph(), run(), chat_loop()
|   |   |-- nodes.py                 <- 6 nÃ³s do grafo (funÃ§Ãµes puras de estado)
|   |   +-- state.py                 <- AgentState TypedDict (estado compartilhado)
|   |
|   |-- ingestion/                   <- pipeline de ingestÃ£o de documentos
|   |   |-- loaders.py               <- load_pdf, load_text, load_markdown, load_directory
|   |   |-- splitter.py              <- dispatcher: PDF->size-based, MD->md_splitter, TXT->txt_splitter
|   |   |-- md_splitter.py           <- chunking por headings ATX Markdown (# ## ###)
|   |   |-- txt_splitter.py          <- chunking por heurÃ­sticas TXT (CAPS, colon, numeraÃ§Ã£o)
|   |   |-- indexer.py               <- Chroma persistente: get_vectorstore, index_chunks, list_indexed_docs
|   |   +-- metadata.py              <- build_chunk_id (SHA-256), normalize_chunk_metadata, build_doc_id
|   |
|   |-- rag/                         <- recuperaÃ§Ã£o e sÃ­ntese RAG
|   |   |-- retriever.py             <- retrieve() â€” MMR/similarity/hybrid + multi-query + reranking
|   |   |-- hybrid.py                <- BM25 index + Reciprocal Rank Fusion (RRF)
|   |   |-- citations.py             <- build_context_block, build_sources_section (breadcrumbs)
|   |   |-- prompts.py               <- todos os prompts: SYSTEM, QA, SUMMARY, COMPARISON, STUDY_PLAN, REPAIR
|   |   |-- query_rewrite.py         <- multi-query: rewrite_queries, multi_query_retrieve
|   |   |-- reranker.py              <- rerank_local (bag-of-words), rerank_llm (Gemini)
|   |   +-- verifier.py              <- verify_grounding: citaÃ§Ãµes, ghost citations, min_citations
|   |
|   |-- grounding/                   <- verificaÃ§Ã£o semÃ¢ntica claim->evidence
|   |   |-- claims.py                <- extract_claims (heuristic/llm/hybrid), extract_cited_claims
|   |   +-- support.py               <- check_support, compute_support_rate (SUPPORTED/NOT_SUPPORTED/UNCLEAR)
|   |
|   |-- tools/                       <- ferramentas do agente
|   |   +-- doc_tools.py             <- tool_search_docs, tool_read_chunk, tool_write_artifact, tool_list_docs
|   |
|   |-- api/                         <- FastAPI application
|   |   |-- app.py                   <- create_app(), CORS, rotas pÃºblicas e protegidas
|   |   |-- schemas.py               <- Pydantic models para request/response
|   |   +-- routes/
|   |       |-- auth.py              <- POST /api/auth/register, /login; GET /api/auth/me
|   |       |-- chat.py              <- POST /api/chat
|   |       |-- ingest.py            <- POST /api/ingest, POST /api/ingest/upload
|   |       |-- docs.py              <- GET /api/docs
|   |       |-- summarize.py         <- POST /api/summarize
|   |       |-- compare.py           <- POST /api/compare
|   |       |-- artifact.py          <- POST /api/artifact, GET /api/artifacts
|   |       +-- health.py            <- GET /api/health
|   |
|   |-- auth/                        <- autenticaÃ§Ã£o JWT
|   |   |-- security.py              <- hash_password (SHA-256+bcrypt), create_access_token, decode_access_token
|   |   +-- dependencies.py          <- get_current_user (FastAPI Depends)
|   |
|   +-- db/                          <- banco de dados SQLAlchemy
|       |-- database.py              <- engine, SessionLocal, Base, get_db, init_db
|       |-- models.py                <- User (id, name, email, password_hash, is_active, created_at)
|       +-- crud.py                  <- get_user_by_email, get_user_by_id, create_user
|
|-- eval/                            <- harness de avaliaÃ§Ã£o (fora do pacote docops)
|   |-- runner.py                    <- EvalRunner, load_suite, mÃ©tricas
|   +-- suites/
|       +-- demo.yaml                <- 11 casos de demo (factual, resumo, abstain)
|
|-- tests/                           <- testes pytest
|   |-- test_api.py
|   |-- test_chroma_ingest.py
|   |-- test_eval.py
|   |-- test_grounding_pipeline.py
|   |-- test_ingest.py
|   |-- test_metadata_persistence.py
|   |-- test_phase2.py
|   |-- test_retriever.py
|   |-- test_semantic_grounding.py
|   |-- test_splitter.py
|   |-- test_structured_splitter.py
|   +-- test_verifier.py
|
|-- docs/                            <- coloque seus documentos aqui (PDF, MD, TXT)
|-- data/
|   |-- chroma/                      <- Ã­ndice ChromaDB persistente (gerado em runtime)
|   +-- bm25/                        <- Ã­ndice BM25 persistente (gerado em runtime)
|-- artifacts/                       <- artefatos gerados pelo agente
+-- web/                             <- frontend React + Vite
    |-- src/
    |-- public/
    |-- index.html
    |-- package.json
    +-- vite.config.ts
```

---

## MÃ³dulos â€” DescriÃ§Ã£o Detalhada

### `docops/config.py`

Singleton `Config` que expÃµe todas as configuraÃ§Ãµes como properties Python. Carrega o `.env` do diretÃ³rio raiz do projeto (nÃ£o do CWD), portanto funciona corretamente independente de onde o comando Ã© executado.

```python
from docops.config import config
config.gemini_api_key    # str
config.chroma_dir        # Path
config.top_k             # int
config.retrieval_mode    # 'mmr' | 'similarity' | 'hybrid'
```

**Regra:** nunca usar `os.getenv()` diretamente no cÃ³digo â€” sempre `config.<propriedade>`.

---

### `docops/graph/state.py` â€” AgentState

`AgentState` Ã© um `TypedDict` com `total=False` â€” cada nÃ³ atualiza apenas os campos que modifica, o LangGraph faz o merge.

| Campo | Tipo | DescriÃ§Ã£o |
|---|---|---|
| `query` | `str` | Query original do usuÃ¡rio |
| `intent` | `str` | Intent classificado: `qa`, `summary`, `comparison`, `checklist`, `study_plan`, `artifact`, `other` |
| `retrieved_chunks` | `List[Document]` | Chunks recuperados do vector store |
| `top_k` | `int` | top_k atual (aumenta a cada retry com +4) |
| `raw_answer` | `str` | Resposta bruta do LLM antes da verificaÃ§Ã£o |
| `context_block` | `str` | Bloco de contexto numerado `[Fonte N]` enviado ao LLM |
| `grounding_ok` | `bool` | Se a verificaÃ§Ã£o de grounding passou |
| `retry` | `bool` | Se deve fazer retry com top_k maior |
| `retry_count` | `int` | NÃºmero de retries realizados |
| `repair_count` | `int` | NÃºmero de passes de repair semÃ¢ntico |
| `disclaimer` | `str` | Disclaimer de baixa confianÃ§a (appended ao answer) |
| `grounding_info` | `dict` | Resultado do grounding semÃ¢ntico: `support_rate`, `unsupported_claims`, `mode`, `results` |
| `grounding` | `dict` | Alias de `grounding_info` para consumers da API |
| `answer` | `str` | Resposta final (raw_answer + disclaimer + fontes) |
| `sources_section` | `str` | SeÃ§Ã£o "Fontes:" formatada |
| `extra` | `dict` | Dados extras para intents especiais (doc_name, topic, context2, summary_mode) |

---

### `docops/graph/graph.py`

Monta e compila o grafo LangGraph. API pÃºblica:

- `build_graph()` â€” constrÃ³i e compila o `StateGraph`
- `get_graph()` â€” lazy singleton do grafo compilado
- `run(query, top_k, extra)` â€” executa uma query e retorna `AgentState` final
- `chat_loop()` â€” loop interativo de chat via CLI (Rich console)

---

### `docops/graph/nodes.py` â€” Os 6 NÃ³s

Cada funÃ§Ã£o recebe `AgentState` e retorna um dict parcial com os campos atualizados.

#### NÃ³ 1: `classify_intent`

Usa o LLM Gemini com `INTENT_CLASSIFICATION_PROMPT` para classificar a query em:
`qa` | `summary` | `comparison` | `checklist` | `study_plan` | `artifact` | `other`

Se o LLM falhar ou retornar intent invÃ¡lido, faz fallback para `qa`.

#### NÃ³ 2: `retrieve_node`

- Para intents `summary`/`comparison` com `doc_name` em `extra`: usa `retrieve_for_doc()` (recupera todos os chunks do documento via filtro Chroma)
- Para demais casos: chama `tool_search_docs(query, top_k)`
- ConstrÃ³i o `context_block` com `build_context_block(chunks)`

#### NÃ³ 3: `synthesize`

Seleciona o prompt correto por intent:

| Intent | Prompt usado |
|---|---|
| `summary` + `summary_mode=brief` | `BRIEF_SUMMARY_PROMPT` |
| `summary` + `summary_mode=deep` | `DEEP_SUMMARY_PROMPT` |
| `comparison` | `COMPARISON_PROMPT` |
| `study_plan` | `STUDY_PLAN_PROMPT` |
| demais | `RAG_SYNTHESIS_PROMPT` |

Chama Gemini com `SystemMessage(SYSTEM_PROMPT)` + `HumanMessage(prompt)`.

#### NÃ³ 4: `verify_grounding_node`

Dois estÃ¡gios de verificaÃ§Ã£o:
1. **Estrutural** via `verify_grounding()` (citaÃ§Ãµes, ghost citations)
2. **SemÃ¢ntico** via `_semantic_grounding_payload()` (claims Ã— evidence)
   - Se `support_rate < MIN_SUPPORT_RATE`: tenta repair com `GROUNDING_REPAIR_PROMPT`
   - Se repair falhar: dispara retry de retrieval (se disponÃ­vel) ou adiciona disclaimer

#### NÃ³ 5: `retry_retrieve`

Incrementa `top_k += 4` e `retry_count += 1`. NÃ£o faz retrieval â€” apenas prepara o estado para o nÃ³ `retrieve` re-executar.

#### NÃ³ 6: `finalize`

Monta a resposta final: `raw_answer + disclaimer + sources_section`. Evita duplicar a seÃ§Ã£o "Fontes:" se ela jÃ¡ estiver no answer.

---

### `docops/ingestion/loaders.py`

Carregadores por tipo de arquivo:

| FunÃ§Ã£o | Formato | Biblioteca | SaÃ­da |
|---|---|---|---|
| `load_pdf(path)` | PDF | pypdf | 1 Document por pÃ¡gina |
| `load_text(path)` | TXT | built-in | 1 Document por arquivo |
| `load_markdown(path)` | MD | built-in | 1 Document por arquivo |
| `load_directory(path)` | qualquer | dispatcher | todos os docs suportados |

ExtensÃµes suportadas: `.pdf`, `.txt`, `.md`, `.markdown`

Todos os Documents carregados jÃ¡ recebem metadados base: `file_name`, `source`, `source_path`, `doc_id`, `file_type`, `page`, `page_start`, `page_end`, `section_title` (vazio), `section_path` (vazio).

---

### `docops/ingestion/splitter.py`

Dispatcher que roteia por extensÃ£o quando `STRUCTURED_CHUNKING=true`:

```
.md / .markdown  -->  md_splitter.split_markdown()    -- por headings ATX
.txt             -->  txt_splitter.split_txt()         -- por heurÃ­sticas
.pdf / outros    -->  RecursiveCharacterTextSplitter   -- size-based
```

Todos os chunks recebem o schema unificado de metadados apÃ³s o split.

---

### `docops/ingestion/md_splitter.py`

Divide arquivos Markdown por headings ATX (`#`, `##`, `###`, atÃ© `######`):
- Detecta headings via regex `^(#{1,6})\s+(.+)$`
- MantÃ©m hierarquia de seÃ§Ãµes (hierarchy dict por nÃ­vel)
- `section_title` = tÃ­tulo da seÃ§Ã£o imediata
- `section_path` = breadcrumb completo, ex.: `"Arquitetura > Retrieval > Reranking"`
- SeÃ§Ãµes maiores que `chunk_size` sÃ£o subdivididas por parÃ¡grafos preservando metadados

---

### `docops/ingestion/txt_splitter.py`

Divide arquivos TXT por heurÃ­sticas â€” detecta headings por:
- Linhas em CAIXA ALTA (â‰¥3 palavras)
- Linhas terminando em `:`
- Linhas com numeraÃ§Ã£o `1.`, `1.1`, `CAPITULO 1`, etc.

Produz `section_title` e `section_path` quando detectado.

---

### `docops/ingestion/indexer.py`

- `get_vectorstore(embeddings)` â€” abre/cria ChromaDB persistente
  - Embedding function: `GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")`
  - Collection name: `"docops"`
- `index_chunks(chunks, incremental)` â€” adiciona chunks ao Chroma
  - Normaliza metadados antes de persistir
  - Enriquece texto com `build_embedding_text()` (prefixo `[meta] section_path\n`)
  - Modo incremental: compara com `ingest_manifest.json` (SHA-256 IDs), pula chunks jÃ¡ indexados
- `list_indexed_docs()` â€” retorna lista de documentos Ãºnicos com `chunk_count`

---

### `docops/ingestion/metadata.py`

- `build_chunk_id(text, meta)` â€” SHA-256 de `source_path + "|" + page_start + "|" + page_end + "|" + section_path + "|" + text[:200]`
- `build_doc_id(source_path)` â€” SHA-256 do path
- `normalize_chunk_metadata(chunk, chunk_index, stable_ids)` â€” garante todos os campos obrigatÃ³rios
- `build_embedding_text(text, meta)` â€” `[meta] section_path\n{text}` para enriquecer o embedding com contexto estrutural
- `infer_file_type(filename)` â€” retorna extensÃ£o normalizada
- `normalize_source_path(path)` â€” path canÃ´nico

---

### `docops/rag/retriever.py`

FunÃ§Ã£o principal de retrieval:

```python
retrieve(query: str, top_k: int | None = None) -> List[Document]
```

Pipeline interno:
1. **Multi-query** (se `MULTI_QUERY=true`): gera N variaÃ§Ãµes â†’ retrieval para cada â†’ deduplica por `chunk_id`
2. **Retrieval base** (`_base_retrieve`):
   - `similarity`: `similarity_search_with_relevance_scores` com filtro de threshold
   - `mmr`: score gate (best score >= threshold) â†’ `max_marginal_relevance_search` com `fetch_k` e `lambda_mult`
   - `hybrid`: `bm25_search` + vector similarity â†’ RRF fusion
3. **Reranking** (se `RERANKER != none`):
   - `local`: rerank_local (bag-of-words overlap)
   - `llm`: rerank_llm (Gemini judge)

`retrieve_for_doc(doc_name, query, top_k)` â€” filtro Chroma por `file_name`, sem threshold/MMR (retorna todos os chunks do documento).

---

### `docops/rag/hybrid.py`

- `build_bm25_index(chunks)` â€” constrÃ³i `BM25Okapi` (tokenizaÃ§Ã£o por lowercase split) e persiste:
  - `data/bm25/bm25_index.pkl` â€” modelo BM25 serializado
  - `data/bm25/bm25_index.json` â€” corpus com `chunk_id`, `text`, `metadata`
- `bm25_search(query, k)` â€” tokeniza query, ranqueia por score BM25, retorna top-k Documents
- `reciprocal_rank_fusion(result_lists, k=60)` â€” score = Î£ `1 / (k + rank + 1)` por chunk_id
- `hybrid_retrieve(query, vector_fn, k_vec, k_lex)` â€” combina BM25 + vector com RRF

---

### `docops/rag/citations.py`

- `build_context_block(chunks)` â€” bloco numerado para o LLM:
  ```
  [Fonte 1] arquivo.md â€” SeÃ§Ã£o > SubseÃ§Ã£o (pÃ¡gina 3)
  <texto do chunk atÃ© CONTEXT_MAX_CHARS>
  ---
  ```
- `build_sources_section(chunks, query)` â€” seÃ§Ã£o **Fontes:** final:
  ```
  **Fontes:**
  - [Fonte 1] **manual.pdf â€” SeÃ§Ã£o > SubseÃ§Ã£o, p. 3 [a1b2c3d4]** â€” _snippet relevante_
  ```
- `extract_evidence_snippet(text, query, window=150)` â€” encontra o trecho com maior overlap de tokens com a query (sliding window de 20 palavras)
- `count_citations_in_answer(answer)` â€” conta `[Fonte N]` no texto
- `max_citation_index(answer)` â€” maior Ã­ndice `[Fonte N]` (para ghost citation detection)
- `_context_text(text)` â€” texto do chunk truncado em `CONTEXT_MAX_CHARS` com word boundary

---

### `docops/rag/prompts.py`

Todos os prompts do sistema (constantes string):

| Constante | Uso |
|---|---|
| `SYSTEM_PROMPT` | System message em todas as interaÃ§Ãµes â€” define regras fundamentais do agente |
| `INTENT_CLASSIFICATION_PROMPT` | Classifica intent em 7 categorias, retorna apenas a palavra |
| `RAG_SYNTHESIS_PROMPT` | QA padrÃ£o com instruÃ§Ãµes de citaÃ§Ã£o `[Fonte N]` |
| `BRIEF_SUMMARY_PROMPT` | Resumo breve (â‰¤300 palavras, palavras-chave ao final) |
| `DEEP_SUMMARY_PROMPT` | Resumo aprofundado com seÃ§Ãµes detalhadas, cobrindo TODO o documento |
| `COMPARISON_PROMPT` | ComparaÃ§Ã£o estruturada: semelhanÃ§as, diferenÃ§as, tabela, conclusÃ£o |
| `STUDY_PLAN_PROMPT` | Plano de estudo: objetivo, prÃ©-requisitos, mÃ³dulos, exercÃ­cios, autoavaliaÃ§Ã£o |
| `GROUNDING_REPAIR_PROMPT` | Reescreve resposta removendo claims sem suporte no contexto |

---

### `docops/rag/verifier.py`

VerificaÃ§Ã£o **estrutural** de grounding (nÃ­vel 1):

- `is_factual_answer(answer)` â€” regex detecta anos, decimais, percentuais, "segundo", "portanto", "define-se", etc.
- `has_min_citations(answer, min_cites)` â€” verifica se tem â‰¥ `MIN_CITATIONS` referÃªncias `[Fonte N]`
- `verify_grounding(state)` â€” orquestraÃ§Ã£o:
  1. Sem chunks â†’ disclaimer + retry (se retry_count < MAX_RETRIES)
  2. Ghost citation (`[Fonte N]` onde N > len(chunks)) â†’ retry
  3. Resposta nÃ£o-factual â†’ grounding_ok=True (sem citaÃ§Ãµes necessÃ¡rias)
  4. Factual mas sem citaÃ§Ãµes suficientes â†’ retry â†’ disclaimer

---

### `docops/rag/reranker.py`

- `rerank_local(query, docs, top_n)` â€” re-score por overlap de tokens query Ã— chunk, ordena e retorna top_n
- `rerank_llm(query, docs, llm, top_n)` â€” envia lista de chunks ao Gemini com pedido de ranking por relevÃ¢ncia

---

### `docops/rag/query_rewrite.py`

- `rewrite_queries(query, llm, n)` â€” prompt ao LLM para gerar N variaÃ§Ãµes da query original
- `multi_query_retrieve(query, retriever_fn, llm, n_variations, per_query_k)` â€” executa retrieval para cada variaÃ§Ã£o, deduplica por `chunk_id`, retorna lista unificada

---

### `docops/grounding/claims.py`

ExtraÃ§Ã£o de afirmaÃ§Ãµes factuais verificÃ¡veis:

- **HeurÃ­stico**: detecta frases com: anos (`\b\d{4}\b`), decimais, percentuais, "segundo", "conforme", "de acordo com", "portanto", "define-se", "consiste", "contÃ©m", "foi criado", etc.
- **LLM**: prompt ao Gemini, retorna JSON `{"claims": [...]}`
- **Hybrid**: heurÃ­stico + LLM, deduplicado por normalizaÃ§Ã£o lowercase

`extract_cited_claims(text)` â€” retorna claims que jÃ¡ tÃªm `[Fonte N]`: `[{"claim": str, "citations": list[str]}]`

---

### `docops/grounding/support.py`

VerificaÃ§Ã£o de suporte semÃ¢ntico claim â†’ evidence:

**HeurÃ­stico** (`_heuristic_support`):
```
score = 0.45 Ã— token_overlap
      + 0.25 Ã— nÃºmero_overlap (ex: "2023", "45%", "3.7")
      + 0.15 Ã— data_overlap (ex: "2023-01-15")
      + 0.10 Ã— entity_overlap (palavras capitalizadas / acrÃ´nimos)
      + 0.05 Ã— unit_overlap (ex: "100ms", "5GB", "R$200")

score >= threshold (0.65)           --> SUPPORTED
score >= threshold * 0.6 (0.39)     --> UNCLEAR
score < threshold * 0.6             --> NOT_SUPPORTED
```

**LLM** (`_llm_support`): Gemini judge com prompt estruturado, retorna JSON `{"label": "SUPPORTED|NOT_SUPPORTED|UNCLEAR", "score": float, "rationale": str}`.

**Hybrid**: heurÃ­stico primeiro; se `UNCLEAR`, chama LLM.

`compute_support_rate(claims, evidence_chunks, mode)`:
- Para cada claim: testa contra todos os chunks, pega o melhor score
- Retorna: `{"support_rate": float, "unsupported_claims": list, "results": list[dict]}`

---

### `docops/tools/doc_tools.py`

Ferramentas do agente (chamadas pelos nÃ³s do grafo ou diretamente pela CLI/API):

| Ferramenta | Assinatura | DescriÃ§Ã£o |
|---|---|---|
| `tool_search_docs` | `(query, top_k) -> List[Document]` | Busca chunks no Chroma via `retrieve()` |
| `tool_read_chunk` | `(chunk_id) -> dict\|None` | LÃª chunk completo por ID diretamente do Chroma (via `collection.get`) |
| `tool_write_artifact` | `(filename, content) -> Path` | Grava conteÃºdo em `artifacts/` â€” sanitiza filename para evitar path traversal |
| `tool_list_docs` | `() -> List[dict]` | Lista documentos indexados com chunk_count |

`tool_write_artifact` tambÃ©m suporta geraÃ§Ã£o de PDF a partir de Markdown via `fpdf2` (quando o arquivo terminar em `.pdf`).

---

### `docops/api/app.py`

Factory da aplicaÃ§Ã£o FastAPI:

```python
app = create_app()
```

- `CORSMiddleware` com origins de `CORS_ORIGINS` (default: `localhost:5173,localhost:3000`)
- `init_db()` no startup â€” cria tabelas SQLite automaticamente (idempotente)
- Rotas **pÃºblicas**: `/api/health`, `/api/auth/*`
- Rotas **protegidas** com `Depends(get_current_user)`: todos os outros endpoints
- URLs: `docs_url="/api/docs-ui"`, `redoc_url="/api/redoc"`, `openapi_url="/api/openapi.json"`

---

### `docops/api/schemas.py`

Todos os Pydantic v2 models:

| Schema | Campos principais |
|---|---|
| `RegisterRequest` | `name` (str, 1-255), `email` (EmailStr), `password` (str, min_length=8) |
| `RegisterResponse` | `id`, `name`, `email`, `created_at` |
| `LoginRequest` | `email` (EmailStr), `password` (str) |
| `LoginResponse` | `access_token` (str), `token_type` (str, default="bearer") |
| `MeResponse` | `id`, `name`, `email`, `created_at` |
| `ChatRequest` | `message` (str, min_length=1), `session_id` (opt), `top_k` (opt, 1-50), `debug_grounding` (bool) |
| `ChatResponse` | `answer`, `sources` (List[SourceItem]), `intent`, `session_id`, `grounding` (opt dict) |
| `SourceItem` | `fonte_n`, `file_name`, `page`, `section_path`, `snippet`, `chunk_id` |
| `IngestPathRequest` | `path` (str), `chunk_size` (int, default=0), `chunk_overlap` (int, default=0) |
| `IngestResponse` | `files_loaded`, `chunks_indexed`, `file_names` |
| `SummarizeRequest` | `doc` (str), `save` (bool), `summary_mode` ("brief"\|"deep") |
| `SummarizeResponse` | `answer`, `artifact_path` (opt) |
| `CompareRequest` | `doc1`, `doc2`, `save` (bool) |
| `CompareResponse` | `answer`, `artifact_path` (opt) |
| `ArtifactRequest` | `type` (str), `topic` (str), `output` (opt str) |
| `ArtifactResponse` | `answer`, `filename`, `path` |
| `HealthResponse` | `status` (default="ok"), `version` (default="0.1.0") |

---

### `docops/api/routes/chat.py`

`POST /api/chat`:
- Executa `run(query, top_k)` em threadpool via `asyncio.to_thread`
- Extrai `SourceItem` list dos chunks do estado
- Inclui `grounding` payload se `debug_grounding=true` ou `DEBUG_GROUNDING=true`

---

### `docops/api/routes/ingest.py`

Dois endpoints:

- `POST /api/ingest` â€” body JSON com `path` (valida contra allowlist `INGEST_ALLOWED_DIRS`)
- `POST /api/ingest/upload` â€” multipart com `files[]` â€” grava em temp dir, ingesta, limpa

Ambos chamam o pipeline: `load_file/directory â†’ split_documents â†’ index_chunks â†’ build_bm25_index`

---

### `docops/auth/security.py`

- `hash_password(password)` â€” `SHA-256(password) â†’ bcrypt.hashpw(prehashed)` (protege contra truncamento silencioso do bcrypt em 72 bytes)
- `verify_password(plain, hashed)` â€” `bcrypt.checkpw(SHA-256(plain), hashed)`
- `normalize_email(email)` â€” lowercase + strip
- `create_access_token(user_id)` â€” JWT `{"sub": str(user_id), "exp": now + expires_minutes}`, assina com `HS256`
- `decode_access_token(token)` â€” decodifica e retorna `user_id` (int)

---

### `docops/db/`

- `database.py` â€” SQLAlchemy engine (SQLite com `check_same_thread=False`), `SessionLocal`, `Base` declarativa, `get_db()` (FastAPI Depends), `init_db()` (cria tabelas)
- `models.py` â€” `User`: `id` (PK), `name`, `email` (unique, indexed), `password_hash`, `is_active` (default True), `created_at` (timezone-aware)
- `crud.py` â€” `get_user_by_email`, `get_user_by_id`, `create_user`

---

## LangGraph Pipeline

```
              +------------------+
   query -->  | classify_intent  |
              +--------+---------+
                       | intent
                       v
              +------------------+
              |    retrieve      |  <--------------------------+
              +--------+---------+                            |
                       | chunks + context_block               |
                       v                                      |
              +------------------+                            |
              |   synthesize     |                            |
              +--------+---------+                            |
                       | raw_answer                           |
                       v                                      |
              +-------------------------+                     |
              |   verify_grounding      |                     |
              +----------+--------------+                     |
                         |                                    |
               +---------+----------+                         |
               | retry=True         | retry=False             |
               v                   v                         |
    +------------------+   +--------------+                  |
    | retry_retrieve   |   |  finalize    |                  |
    | top_k += 4       |   +--------------+                  |
    | retry_count += 1 |         |                           |
    +--------+---------+         v                           |
             |              answer final                     |
             +--------------------------------------------->-+
```

**LÃ³gica de retry (estrutural):**
- `grounding_ok=False` + `retry_count < MAX_RETRIES` â†’ `retry=True` â†’ `retry_retrieve` â†’ volta para `retrieve` com `top_k` maior

**LÃ³gica de repair (semÃ¢ntico):**
- `support_rate < MIN_SUPPORT_RATE` + `repair_count < GROUNDING_REPAIR_MAX_PASSES` â†’ reescreve answer com `GROUNDING_REPAIR_PROMPT`
- ApÃ³s repair: re-verifica grounding bÃ¡sico + recalcula support_rate
- Se ainda baixo + retries disponÃ­veis â†’ `retry=True`
- Se esgotado â†’ disclaimer `"âš ï¸ Aviso: A resposta foi limitada a evidÃªncias parcialmente suportadas"`

---

## Ingestion Pipeline

```
Arquivos em docs/
      |
      v
load_directory(path)                  -- load_pdf / load_text / load_markdown
      |  List[Document]
      v
split_documents(docs, chunk_size, chunk_overlap)
      |  dispatcher por extensÃ£o
      +-- .md   --> md_splitter.split_markdown()    -- por headings ATX
      +-- .txt  --> txt_splitter.split_txt()         -- por heurÃ­sticas
      +-- .pdf  --> RecursiveCharacterTextSplitter   -- size-based
      |  List[Document] com metadados unificados
      v
index_chunks(chunks)
      |
      +-- normalize_chunk_metadata() --> chunk_id SHA-256 estÃ¡vel
      +-- build_embedding_text()     --> prefixo "[meta] section_path\n"
      +-- Chroma.add_documents()     --> vetores + metadados persistidos em data/chroma/
      +-- ingest_manifest.json       --> tracking de IDs para modo incremental
      |
      v
build_bm25_index(chunks)
      +-- BM25Okapi --> data/bm25/bm25_index.pkl
      +-- corpus    --> data/bm25/bm25_index.json
```

### Schema de Metadados dos Chunks

Todos os chunks (PDF, MD, TXT) recebem obrigatoriamente:

```python
{
    "file_name": str,        # "manual.pdf"
    "source": str,           # path absoluto
    "source_path": str,      # path absoluto (alias)
    "doc_id": str,           # SHA-256 do arquivo
    "file_type": str,        # "pdf" | "md" | "txt"
    "page": str | int,       # nÃºmero da pÃ¡gina ou "N/A"
    "page_start": str | int, # inÃ­cio do intervalo de pÃ¡ginas
    "page_end": str | int,   # fim do intervalo de pÃ¡ginas
    "section_title": str,    # tÃ­tulo da seÃ§Ã£o (MD/TXT) ou ""
    "section_path": str,     # breadcrumb "SeÃ§Ã£o > SubseÃ§Ã£o" ou ""
    "chunk_id": str,         # SHA-256 estÃ¡vel
    "chunk_index": int,      # Ã­ndice sequencial
}
```

---

## RAG â€” Retrieval-Augmented Generation

### Modos de Retrieval

| Modo | Como funciona | Quando usar |
|---|---|---|
| `similarity` | Cosine similarity com threshold | Baseline, mais simples |
| `mmr` | Max Marginal Relevance â€” diversidade + relevÃ¢ncia | PadrÃ£o â€” evita chunks redundantes |
| `hybrid` | BM25 lexical + vector semantic via RRF | Melhor recall, especialmente para termos tÃ©cnicos exatos |

### Contexto para o LLM

`build_context_block` formata:

```
[Fonte 1] manual.pdf â€” Arquitetura > Retrieval (pÃ¡gina 3)
<texto do chunk atÃ© CONTEXT_MAX_CHARS caracteres>
---

[Fonte 2] outro_doc.md â€” IntroduÃ§Ã£o (sem pÃ¡gina)
<texto>
---
```

### SeÃ§Ã£o Fontes na Resposta

`build_sources_section` gera:

```
**Fontes:**
- [Fonte 1] **manual.pdf â€” Arquitetura > Retrieval, p. 3 [a1b2c3d4]** â€” _snippet relevante_
- [Fonte 2] **outro_doc.md â€” IntroduÃ§Ã£o [e5f6g7h8]** â€” _snippet_
```

O snippet Ã© extraÃ­do por `extract_evidence_snippet` que localiza o trecho com maior overlap de tokens com a query original (nÃ£o apenas o inÃ­cio do chunk).

---

## Grounding Verifier SemÃ¢ntico

### Dois NÃ­veis

**NÃ­vel 1 â€” Estrutural** (`rag/verifier.py`):
- Detecta ghost citations: `[Fonte N]` onde N > nÃºmero de chunks recuperados
- Verifica mÃ­nimo de citaÃ§Ãµes (`MIN_CITATIONS`)
- Triggers retry com `top_k` maior

**NÃ­vel 2 â€” SemÃ¢ntico** (`grounding/`):
- Extrai claims factuais da resposta
- Verifica suporte de cada claim contra os chunks de evidÃªncia
- Calcula `support_rate = claims_SUPPORTED / total_claims`
- Se baixo: tenta repair â†’ retry â†’ disclaimer

### Modos de VerificaÃ§Ã£o (`GROUNDED_VERIFIER_MODE`)

| Modo | Custo | Quando usar |
|---|---|---|
| `heuristic` | Sem API | Desenvolvimento, CI, produÃ§Ã£o com baixo custo |
| `llm` | API Gemini por claim | MÃ¡xima precisÃ£o |
| `hybrid` | API sÃ³ quando UNCLEAR | EquilÃ­brio custo/precisÃ£o |

---

## API REST (FastAPI)

### Rotas pÃºblicas (sem autenticaÃ§Ã£o)

| MÃ©todo | Rota | DescriÃ§Ã£o |
|---|---|---|
| `GET` | `/api/health` | Status: `{"status": "ok", "version": "0.1.0"}` |
| `POST` | `/api/auth/register` | Cadastra usuÃ¡rio. Body: `{"name": "...", "email": "...", "password": "..."}` |
| `POST` | `/api/auth/login` | Login. Body: `{"email": "...", "password": "..."}`. Retorna `{"access_token": "...", "token_type": "bearer"}` |

### Rotas protegidas (requerem `Authorization: Bearer <token>`)

| MÃ©todo | Rota | Body | DescriÃ§Ã£o |
|---|---|---|---|
| `GET` | `/api/auth/me` | â€” | Dados do usuÃ¡rio logado |
| `GET` | `/api/docs` | â€” | Lista documentos indexados com chunk_count |
| `POST` | `/api/ingest` | `{"path": "/abs/path", "chunk_size": 0, "chunk_overlap": 0}` | Ingere documentos de path no servidor |
| `POST` | `/api/ingest/upload` | multipart `files[]` + `chunk_size` + `chunk_overlap` | Upload e ingestÃ£o de arquivos |
| `POST` | `/api/chat` | `{"message": "...", "top_k": null, "debug_grounding": false}` | Envia mensagem ao agente |
| `POST` | `/api/summarize` | `{"doc": "arquivo.pdf", "save": false, "summary_mode": "brief"}` | Gera resumo de documento |
| `POST` | `/api/compare` | `{"doc1": "a.pdf", "doc2": "b.pdf", "save": false}` | Compara dois documentos |
| `POST` | `/api/artifact` | `{"type": "study_plan", "topic": "...", "output": null}` | Gera artefato estruturado |
| `GET` | `/api/artifacts` | â€” | Lista artefatos gerados em `artifacts/` |

### Swagger UI

DisponÃ­vel em `http://localhost:8000/api/docs-ui` com todos os endpoints documentados e testÃ¡veis.

---

## AutenticaÃ§Ã£o (JWT + SQLite)

### Fluxo completo

```
1. POST /api/auth/register
   body: {name, email, password}
   --> create_user (hash: SHA-256 + bcrypt)
   --> 201 Created: {id, name, email, created_at}

2. POST /api/auth/login
   body: {email, password}
   --> verify_password (SHA-256 + bcrypt.checkpw)
   --> create_access_token (JWT HS256, exp = now + JWT_EXPIRES_MINUTES)
   --> 200 OK: {access_token, token_type: "bearer"}

3. RequisiÃ§Ãµes protegidas:
   header: Authorization: Bearer <token>
   --> get_current_user (decode_access_token)
   --> get_user_by_id (DB lookup)
   --> injeta User no handler via Depends
```

### Modelo User (SQLite)

```python
class User(Base):
    __tablename__ = "users"
    id: int               # PK autoincrement
    name: str             # max 255 chars
    email: str            # unique, indexed
    password_hash: str    # bcrypt hash
    is_active: bool       # default True
    created_at: datetime  # timezone-aware UTC
```

### MigraÃ§Ã£o para PostgreSQL (produÃ§Ã£o)

```bash
pip install psycopg2-binary
# No .env:
DATABASE_URL=postgresql+psycopg2://usuario:senha@localhost:5432/docops
# Reiniciar o servidor â€” tabelas criadas automaticamente
```

---

## Frontend (React + Vite)

LocalizaÃ§Ã£o: `DocOps_Agent/web/`

```bash
npm run dev    # desenvolvimento: http://localhost:5173
npm run build  # build de produÃ§Ã£o em web/dist/
npm run lint   # ESLint
```

O frontend comunica com a API em `http://localhost:8000`. Armazena o JWT em `localStorage` (MVP â€” para produÃ§Ã£o: cookie httpOnly).

**Importante:** se o Vite subir em porta diferente de `5173` (ex: `5174` por conflito), adicione ao `.env`:
```
CORS_ORIGINS=http://localhost:5173,http://localhost:5174,http://localhost:3000
```

---

## CLI â€” Comandos

Todos executados na pasta `DocOps_Agent/` com `.venv` ativo:

```bash
# IngestÃ£o
python -m docops ingest --path docs/
python -m docops ingest --file docs/manual.pdf
python -m docops ingest --path docs/ --chunk-size 600 --chunk-overlap 100

# Chat interativo (terminal)
python -m docops chat
python -m docops chat --debug-grounding   # mostra payload de grounding

# Listar documentos indexados
python -m docops list-docs

# Resumo (brief ou deep)
python -m docops summarize --doc manual.pdf
python -m docops summarize --doc manual.pdf --save

# ComparaÃ§Ã£o
python -m docops compare --doc1 v1.pdf --doc2 v2.pdf
python -m docops compare --doc1 v1.pdf --doc2 v2.pdf --save

# GeraÃ§Ã£o de artefatos
python -m docops artifact --type study_plan --topic "Redes Neurais"
python -m docops artifact --type checklist --topic "Deploy em produÃ§Ã£o" --output deploy.md

# Eval
python -m docops eval --suite demo --mock            # sem API (para CI)
python -m docops eval --suite demo                   # com API
python -m docops eval --suite demo --retrieval hybrid --rerank on --k 8
python -m docops eval --suite demo --strict          # falha se strict_pass_rate < 1.0

# Servidor web
python -m docops serve
python -m docops serve --host 0.0.0.0 --port 8080 --reload
```

---

## Benchmark de Deep Summary

Script reproduzível para medir latência e qualidade por perfil de execução (`fast`, `model_first`, `strict`).

### Como rodar

```bash
# Com o servidor rodando em http://127.0.0.1:8000
python eval/benchmark_deep_summary.py \
  --doc "meu_documento.pdf" \
  --email usuario@exemplo.com \
  --password minha_senha \
  --profiles fast,model_first,strict \
  --runs 10 \
  --warmup 1
```

### Parâmetros principais

| Parâmetro | Default | Descrição |
|---|---|---|
| `--doc` | obrigatório | Nome do documento no sistema (`file_name`) |
| `--profiles` | `fast,model_first,strict` | Perfis separados por vírgula |
| `--runs` | `10` | Rodadas medidas por perfil |
| `--warmup` | `1` | Rodadas de aquecimento (não contabilizadas) |
| `--base-url` | `http://127.0.0.1:8000` | URL base da API |
| `--email` / `--password` | obrigatórios | Credenciais para login |
| `--out-json` | `artifacts/benchmarks/benchmark_<ts>.json` | Relatório JSON completo |
| `--out-md` | `artifacts/benchmarks/benchmark_<ts>.md` | Relatório Markdown executivo |
| `--accepted-threshold` | `0.8` | Taxa mínima de `accepted` para qualificar perfil |

### Onde achar os relatórios

```
artifacts/
└── benchmarks/
    ├── benchmark_20260312_103045.json   # amostras brutas + agregados
    └── benchmark_20260312_103045.md     # tabela comparativa + recomendação
```

### Regra de recomendação automática

1. Filtra perfis com `accepted_rate >= threshold` (default 0.8).
2. Entre os qualificados, escolhe o de menor `p95_ms`.
3. Se nenhum atingir o threshold, escolhe o de maior `accepted_rate` e emite flag de risco.

---

## Eval Harness

LocalizaÃ§Ã£o: `eval/runner.py`, suites em `eval/suites/`.

### MÃ©tricas

| MÃ©trica | Como Ã© calculada |
|---|---|
| `CitationCoverage` | FraÃ§Ã£o de frases factuais com â‰¥1 citaÃ§Ã£o `[Fonte N]` |
| `CitationSupportRate` | FraÃ§Ã£o das citaÃ§Ãµes com suporte semÃ¢ntico SUPPORTED |
| `AbstentionAccuracy` | Agente abstÃ©m corretamente quando `expected=""` |
| `RetrievalRecall proxy` | FraÃ§Ã£o de termos da pergunta presentes nos chunks recuperados |
| `MustCitePass` | PadrÃµes obrigatÃ³rios de citaÃ§Ã£o presentes na resposta |
| `StrictPassRate` | Casos factual com CitationCoverage=1.0 |

### Formato de suite YAML

```yaml
suite_name: minha_suite
description: "DescriÃ§Ã£o opcional"
cases:
  - id: factual_01
    question: "Em que ano o produto foi lanÃ§ado?"
    tags: [factual, numbers]

  - id: abstain_01
    question: "Qual Ã© o preÃ§o?"
    expected: ""        # agente deve dizer que nÃ£o encontrou
    tags: [abstain]

  - id: must_cite_01
    question: "O que Ã© RAG?"
    must_cite: true     # resposta deve conter [Fonte N]
    tags: [factual]
```

### Modo mock (sem API)

```bash
python -m docops eval --suite demo --mock
```

Usa um stub agent que retorna abstention padrÃ£o â€” Ãºtil para CI sem gastos de API.

---

## Testes

```bash
# Na pasta DocOps_Agent/, com .venv ativo
pytest

# Verbose com nomes dos testes
pytest -v

# Teste especÃ­fico
pytest tests/test_structured_splitter.py -v
pytest tests/test_semantic_grounding.py -v
pytest tests/test_eval.py -v
pytest tests/test_api.py -v
```

### Cobertura dos testes

| Arquivo | O que testa |
|---|---|
| `test_api.py` | Endpoints FastAPI (register, login, chat, ingest) com `TestClient` |
| `test_chroma_ingest.py` | Ingestion com `FakeEmbeddings` determinÃ­sticos â€” sem chamadas Ã  API |
| `test_eval.py` | EvalRunner com mock agent â€” sem chamadas Ã  API |
| `test_grounding_pipeline.py` | Pipeline completo de grounding semÃ¢ntico |
| `test_ingest.py` | Loaders + splitter |
| `test_metadata_persistence.py` | PersistÃªncia e consistÃªncia de metadados nos chunks |
| `test_phase2.py` | Multi-query, hybrid search, reranking |
| `test_retriever.py` | Modos de retrieval |
| `test_semantic_grounding.py` | `claims.py` + `support.py` (extraÃ§Ã£o + suporte) |
| `test_splitter.py` | `RecursiveCharacterTextSplitter` base |
| `test_structured_splitter.py` | MD/TXT splitters + dispatcher |
| `test_verifier.py` | `verify_grounding` â€” citaÃ§Ãµes, ghost citations, min_citations |

> Testes de Chroma usam `FakeEmbeddings` determinÃ­sticos â€” **nenhuma chamada Ã  API Gemini** Ã© feita.

---

## DependÃªncias

Definidas em `pyproject.toml` (`requires-python = ">=3.11"`):

| Pacote | VersÃ£o | Para que serve |
|---|---|---|
| `langchain` | >=1.0.0 | Framework RAG base |
| `langchain-text-splitters` | >=1.0.0 | RecursiveCharacterTextSplitter |
| `langchain-google-genai` | >=4.0.0 | Gemini LLM + embeddings |
| `langchain-chroma` | >=0.1.0 | LangChain wrapper para ChromaDB |
| `langgraph` | >=1.0.0 | OrquestraÃ§Ã£o do agente (StateGraph) |
| `chromadb` | >=0.5.0,<0.6.0 | Vector store persistente |
| `pypdf` | >=4.0.0 | Leitura de PDFs |
| `python-dotenv` | >=1.0.0 | Carregamento do .env |
| `typer` | >=0.12.0 | CLI |
| `rich` | >=13.0.0 | Output formatado no terminal |
| `pydantic` | >=2.0.0 | ValidaÃ§Ã£o de dados |
| `fastapi` | >=0.111.0 | API Web |
| `uvicorn[standard]` | >=0.29.0 | Servidor ASGI |
| `python-multipart` | >=0.0.9 | Upload de arquivos multipart |
| `rank-bm25` | >=0.2.2 | BM25Okapi para hybrid search |
| `pyyaml` | >=6.0.0 | Leitura de suites YAML de eval |
| `SQLAlchemy` | >=2.0.0 | ORM para banco de dados |
| `bcrypt` | >=4.0.1 | Hash de senhas |
| `PyJWT` | >=2.8.0 | Tokens JWT |
| `email-validator` | >=2.0.0 | ValidaÃ§Ã£o de e-mail (Pydantic EmailStr) |

Dev:

| Pacote | Para que serve |
|---|---|
| `pytest` | Framework de testes |
| `pytest-asyncio` | Suporte a testes assÃ­ncronos |

---

## Roadmap

- [x] Interface web (FastAPI + React)
- [x] Multi-query retrieval
- [x] Reranking (local + LLM)
- [x] Hybrid search (BM25 + vector)
- [x] Stable IDs + incremental ingest
- [x] Structured chunking (MD/TXT por seÃ§Ãµes)
- [x] Semantic grounding verifier (claim->evidence)
- [x] Eval harness com mÃ©tricas
- [x] AutenticaÃ§Ã£o JWT + SQLite
- [ ] HistÃ³rico de conversas por sessÃ£o
- [ ] Suporte a mais formatos (DOCX, HTML)
- [ ] Rate limiting
- [ ] Deploy containerizado (Docker)
