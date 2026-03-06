# DocOps Agent

> **Document Operations Agent** Ã¢â‚¬â€ RAG + LangGraph + Google Gemini + Chroma

Agente conversacional que opera sobre seus documentos tÃƒÂ©cnicos usando Retrieval-Augmented Generation (RAG). Indexa PDFs, Markdown e TXT em um Chroma persistente e responde perguntas com citaÃƒÂ§ÃƒÂµes rastreÃƒÂ¡veis, verificaÃƒÂ§ÃƒÂ£o de fundamentaÃƒÂ§ÃƒÂ£o e suporte a mÃƒÂºltiplos intents (QA, resumo, comparaÃƒÂ§ÃƒÂ£o, plano de estudos, artefatos).

---

## PrÃƒÂ©-requisitos

| Requisito | VersÃƒÂ£o |
|---|---|
| Python | **3.11 ou 3.12** (ChromaDB requer Ã¢â€°Â¤ 3.13; veja nota abaixo) |
| Google Gemini API Key | [ai.google.dev](https://ai.google.dev/) |

> **Nota Python 3.14+:** Se o seu sistema tiver Python 3.14 instalado, crie o venv explicitamente com 3.11 ou 3.12:
> ```bash
> py -3.11 -m venv .venv
> ```

---

## InstalaÃƒÂ§ÃƒÂ£o

```bash
# 1. Clone o repositÃƒÂ³rio
git clone <repo-url>
cd docops-agent

# 2. Crie e ative o ambiente virtual (use Python 3.11 ou 3.12)
py -3.11 -m venv .venv          # Windows
source .venv/Scripts/activate   # Windows (Git Bash / PowerShell: .venv\Scripts\activate)

# 3. Instale as dependÃƒÂªncias
pip install -r requirements.txt

# 4. Configure as variÃƒÂ¡veis de ambiente
cp .env.example .env
# Edite .env e preencha GEMINI_API_KEY
```

---

## ConfiguraÃƒÂ§ÃƒÂ£o (`.env`)

| VariÃƒÂ¡vel | PadrÃƒÂ£o | DescriÃƒÂ§ÃƒÂ£o |
|---|---|---|
| `GEMINI_API_KEY` | **(obrigatÃƒÂ³rio)** | Chave da API Google Gemini |
| `CHROMA_DIR` | `./data/chroma` | DiretÃƒÂ³rio de persistÃƒÂªncia do Chroma |
| `DOCS_DIR` | `./docs` | Pasta com documentos a indexar |
| `ARTIFACTS_DIR` | `./artifacts` | Onde os artefatos gerados sÃƒÂ£o salvos |
| `TOP_K` | `6` | NÃƒÂºmero de chunks recuperados por query |
| `CHUNK_SIZE` | `900` | Tamanho de cada chunk (tokens) |
| `CHUNK_OVERLAP` | `150` | SobreposiÃƒÂ§ÃƒÂ£o entre chunks |
| `LOG_LEVEL` | `INFO` | NÃƒÂ­vel de log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Modelo Gemini para sÃƒÂ­ntese |
| *(embedding)* | `models/gemini-embedding-001` | Embedding model (hardcoded, ÃƒÂºnico disponÃƒÂ­vel na API) |
| `RETRIEVAL_MODE` | `mmr` | Modo de retrieval: `mmr`, `similarity` ou `hybrid` (BM25 + vector) |
| `MIN_RELEVANCE_SCORE` | `0.2` | Score mÃƒÂ­nimo de relevÃƒÂ¢ncia Ã¢â‚¬â€ chunks abaixo sÃƒÂ£o descartados |
| `MMR_FETCH_K` | `top_k Ãƒâ€” 4` | Candidatos buscados antes do re-ranking MMR |
| `MMR_LAMBDA` | `0.5` | BalanÃƒÂ§o MMR: 0 = diversidade mÃƒÂ¡x, 1 = relevÃƒÂ¢ncia mÃƒÂ¡x |
| `CONTEXT_MAX_CHARS` | `1500` | MÃƒÂ¡x de chars do chunk no contexto do LLM (0 = sem limite) |
| `MULTI_QUERY` | `false` | Multi-query: reescreve a query em N variaÃƒÂ§ÃƒÂµes para maior recall |
| `MULTI_QUERY_N` | `3` | NÃƒÂºmero de variaÃƒÂ§ÃƒÂµes de query |
| `MULTI_QUERY_PER_QUERY_K` | `top_k` | top_k por variaÃƒÂ§ÃƒÂ£o individual |
| `RERANKER` | `none` | Modo de reranking: `none`, `local` (bag-of-words) ou `llm` (Gemini) |
| `RERANK_TOP_N` | `top_k` | Documentos a manter apÃƒÂ³s reranking |
| `BM25_DIR` | `./data/bm25` | DiretÃƒÂ³rio do ÃƒÂ­ndice BM25 persistente |
| `HYBRID_K_LEX` | `top_k` | NÃƒÂºmero de resultados BM25 no modo hybrid |
| `HYBRID_ALPHA` | `0.5` | Peso (reservado; RRF usado por padrÃƒÂ£o) |
| `INGEST_INCREMENTAL` | `false` | Pular re-indexaÃƒÂ§ÃƒÂ£o de chunks inalterados (IDs SHA-256 estÃƒÂ¡veis) |
| `STRUCTURED_CHUNKING` | `true` | Chunking estruturado por seÃƒÂ§ÃƒÂ£o para MD/TXT |
| `SEMANTIC_GROUNDING_ENABLED` | `true` | Verificador semÃƒÂ¢ntico claimÃ¢â€ â€™evidence |
| `GROUNDED_VERIFIER_MODE` | `heuristic` | Modo: `heuristic`, `llm`, `hybrid` |
| `GROUNDED_VERIFIER_THRESHOLD` | `0.65` | Minimum heuristic support threshold |
| `GROUNDED_CLAIMS_MODE` | `heuristic` | Claim extraction mode: `heuristic`, `llm`, `hybrid` |
| `MIN_SUPPORT_RATE` | `0.5` | Minimum support rate before semantic repair/retry |
| `GROUNDING_REPAIR_MAX_PASSES` | `1` | Maximum number of semantic repair passes |
| `GROUNDING_RETRIEVAL_MAX_RETRIES` | `1` | Retrieval retries triggered by semantic grounding |
| `DEBUG_GROUNDING` | `false` | Expose grounding payload in API/CLI debug mode |
| `EVAL_SUITES_DIR` | `./eval/suites` | DiretÃƒÂ³rio com suites YAML de avaliaÃƒÂ§ÃƒÂ£o |
| `EVAL_OUTPUT_DIR` | `./artifacts` | DiretÃƒÂ³rio de saÃƒÂ­da dos relatÃƒÂ³rios de eval |

---

## Arquitetura

```
UsuÃƒÂ¡rio
  Ã¢â€â€š
  Ã¢â€“Â¼
CLI (typer/rich)
  Ã¢â€â€š
  Ã¢â€“Â¼
LangGraph Ã¢â‚¬â€ grafo de estados
  Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ classify_intent   Ã¢â€ â€™ detecta intent (qa/summary/comparison/Ã¢â‚¬Â¦)
  Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ retrieve          Ã¢â€ â€™ tool_search_docs Ã¢â€ â€™ Chroma MMR/similarity/hybrid + score threshold + reranking
  Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ synthesize        Ã¢â€ â€™ Gemini LLM + prompt especializado
  Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ verify_grounding  Ã¢â€ â€™ verifica citaÃƒÂ§ÃƒÂµes e factualidade
  Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ retry_retrieve    Ã¢â€ â€™ repete com top_k maior se necessÃƒÂ¡rio
  Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ finalize          Ã¢â€ â€™ monta resposta + seÃƒÂ§ÃƒÂ£o "Fontes:"
```

### Fluxo MVP

1. **IngestÃƒÂ£o**: `load_directory/load_file` Ã¢â€ â€™ `split_documents` (IDs SHA-256 estÃƒÂ¡veis) Ã¢â€ â€™ `index_chunks` (Chroma) + `build_bm25_index` (BM25)
2. **Chat**: query Ã¢â€ â€™ [multi-query rewriting] Ã¢â€ â€™ grafo LangGraph Ã¢â€ â€™ [reranking] Ã¢â€ â€™ resposta com fontes rastreÃƒÂ¡veis
3. **VerificaÃƒÂ§ÃƒÂ£o**: `verify_grounding` confere citaÃƒÂ§ÃƒÂµes, detecta citaÃƒÂ§ÃƒÂµes fantasmas (`[Fonte N]` > total de chunks), retries automÃƒÂ¡ticos

---

## Estrutura de Pastas

```
docops-agent/
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ docops/
Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ __init__.py
Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ __main__.py          # python -m docops
Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ cli.py               # Comandos CLI (typer)
Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ config.py            # Leitura de env vars
Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ logging.py           # Logger configurÃƒÂ¡vel via LOG_LEVEL
Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ graph/
Ã¢â€â€š   Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ graph.py         # Montagem e execuÃƒÂ§ÃƒÂ£o do grafo LangGraph
Ã¢â€â€š   Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ nodes.py         # NÃƒÂ³s do grafo (funÃƒÂ§ÃƒÂµes de estado)
Ã¢â€â€š   Ã¢â€â€š   Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ state.py         # AgentState (TypedDict)
Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ ingestion/
Ã¢â€â€š   Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ indexer.py       # Chroma persistente (get_vectorstore, index_chunks)
Ã¢â€â€š   Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ loaders.py       # Carregamento de PDF, MD, TXT
Ã¢â€â€š   Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ splitter.py      # Dispatcher + chunking genÃƒÂ©rico (PDF)
Ã¢â€â€š   Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ md_splitter.py   # Chunking por headings (Markdown)
Ã¢â€â€š   Ã¢â€â€š   Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ txt_splitter.py  # Chunking por heurÃƒÂ­sticas (TXT)
Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ grounding/
Ã¢â€â€š   Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ claims.py        # ExtraÃƒÂ§ÃƒÂ£o de claims factuais sem citaÃƒÂ§ÃƒÂ£o
Ã¢â€â€š   Ã¢â€â€š   Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ support.py       # Verificador claimÃ¢â€ â€™evidence (heurÃƒÂ­stico/LLM/hybrid)
Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ rag/
Ã¢â€â€š   Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ citations.py     # build_context_block, build_sources_section (com breadcrumbs)
Ã¢â€â€š   Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ hybrid.py        # BM25 index + Reciprocal Rank Fusion
Ã¢â€â€š   Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ prompts.py       # Prompts para cada intent
Ã¢â€â€š   Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ query_rewrite.py # Multi-query: rewrite_queries, multi_query_retrieve
Ã¢â€â€š   Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ reranker.py      # Reranking: local (BoW) e LLM
Ã¢â€â€š   Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ retriever.py     # retrieve() com multi-query, hybrid, reranking
Ã¢â€â€š   Ã¢â€â€š   Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ verifier.py      # verify_grounding (citaÃƒÂ§ÃƒÂµes + fantasmas + factualidade)
Ã¢â€â€š   Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ tools/
Ã¢â€â€š       Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ doc_tools.py     # tool_search_docs, tool_read_chunk, tool_write_artifact, tool_list_docs
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ eval/
Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ runner.py            # EvalRunner + mÃƒÂ©tricas (CitationCoverage, SupportRate, Ã¢â‚¬Â¦)
Ã¢â€â€š   Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ suites/
Ã¢â€â€š       Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ demo.yaml        # Suite demo com 11 casos (factual, resumo, localizaÃƒÂ§ÃƒÂ£o, abstain)
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ tests/
Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ test_chroma_ingest.py         # Testes de ingestÃƒÂ£o Chroma com FakeEmbeddings
Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ test_ingest.py
Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ test_retriever.py
Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ test_splitter.py
Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ test_structured_splitter.py   # MD/TXT splitters + dispatcher
Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ test_semantic_grounding.py    # claims.py + support.py
Ã¢â€â€š   Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ test_eval.py                  # eval harness (mock agent)
Ã¢â€â€š   Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ test_verifier.py
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ docs/                    # Coloque seus documentos aqui (ignorado pelo git)
Ã¢â€â€š   Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ .gitkeep
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ data/chroma/             # ÃƒÂndice Chroma persistente (gerado em runtime, ignorado pelo git)
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ artifacts/               # Artefatos gerados (ignorado pelo git)
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ .env.example
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ pyproject.toml
Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ requirements.txt
```

---

## Ferramentas (Tools)

| Ferramenta | DescriÃƒÂ§ÃƒÂ£o |
|---|---|
| `tool_search_docs(query, top_k)` | Busca chunks relevantes no Chroma (MMR ou similarity + score threshold); retorna `List[Document]` com metadata (chunk_id, file_name, page, source, retrieval_score) |
| `tool_read_chunk(chunk_id)` | LÃƒÂª um chunk completo por ID direto do Chroma |
| `tool_write_artifact(filename, content)` | Grava conteÃƒÂºdo em `artifacts/` |
| `tool_list_docs()` | Lista todos os documentos indexados com contagem de chunks |

---

## Structured Chunking

Quando `STRUCTURED_CHUNKING=true` (padrÃƒÂ£o), arquivos MD e TXT sÃƒÂ£o divididos por estrutura de seÃƒÂ§ÃƒÂ£o em vez de apenas por tamanho.

### Markdown (`.md`)
- Divide por headings ATX (`#`, `##`, `###`, etc.)
- Cada chunk recebe `section_title` e `section_path` (breadcrumb), ex.: `"Arquitetura > Retrieval > Reranking"`
- SeÃƒÂ§ÃƒÂµes grandes sÃƒÂ£o subdivididas mantendo os metadados

### TXT (`.txt`)
- Detecta "headings" por: linhas em CAIXA ALTA, linhas terminando em `:`, numeraÃƒÂ§ÃƒÂ£o `1.` / `1.1`
- Produz `section_title` e `section_path` quando detectado

### Schema de metadados

Todos os chunks (PDF, MD, TXT) recebem:
```
file_type, page, page_start, page_end
section_title, section_path
chunk_id (SHA-256 estÃƒÂ¡vel), chunk_index
```

### Fontes com breadcrumbs

```
- [Fonte 1] **manual.md Ã¢â‚¬â€ Arquitetura > Retrieval, p. 3** Ã¢â‚¬â€ _snippet_
```

---

## Grounding verifier

O mÃƒÂ³dulo `docops/grounding/` verifica se os trechos citados **suportam** as afirmaÃƒÂ§ÃƒÂµes, nÃƒÂ£o apenas se existem.

### Pipeline
1. **ExtraÃƒÂ§ÃƒÂ£o de claims** (`claims.py`): frases factuais sem citaÃƒÂ§ÃƒÂ£o `[Fonte N]`
2. **VerificaÃƒÂ§ÃƒÂ£o de suporte** (`support.py`): heurÃƒÂ­stico (overlap + nÃƒÂºmeros) ou LLM
3. **Repair pass**: se `CitationSupportRate < MIN_SUPPORT_RATE`, dispara retry

### Modos (`GROUNDED_VERIFIER_MODE`)
| Modo | DescriÃƒÂ§ÃƒÂ£o |
|---|---|
| `heuristic` | Overlap de tokens + consistÃƒÂªncia numÃƒÂ©rica (sem API) |
| `llm` | Juiz Gemini com output JSON |
| `hybrid` | HeurÃƒÂ­stico primeiro; LLM sÃƒÂ³ quando UNCLEAR |

---

## Evaluation

```bash
# Suite demo em modo mock (sem API)
python -m docops.eval --suite demo --mock

# Suite real
python -m docops.eval --suite demo --retrieval hybrid --rerank on --k 8

# Modo estrito (falha CI se coverage < 100%)
python -m docops.eval --suite demo --strict
```

### MÃƒÂ©tricas
| MÃƒÂ©trica | DescriÃƒÂ§ÃƒÂ£o |
|---|---|
| `CitationCoverage` | FraÃƒÂ§ÃƒÂ£o de frases factuais com Ã¢â€°Â¥1 citaÃƒÂ§ÃƒÂ£o `[Fonte N]` |
| `CitationSupportRate` | FraÃƒÂ§ÃƒÂ£o das citaÃƒÂ§ÃƒÂµes com suporte semÃƒÂ¢ntico SUPPORTED |
| `AbstentionAccuracy` | Agente abstÃƒÂ©m corretamente quando nÃƒÂ£o hÃƒÂ¡ resposta |
| `RetrievalRecall proxy` | Termos da pergunta presentes em chunks recuperados |
| `MustCitePass` | PadrÃƒÂµes obrigatÃƒÂ³rios de citaÃƒÂ§ÃƒÂ£o presentes na resposta |

### Criar uma suite

```yaml
suite_name: minha_suite
cases:
  - id: factual_01
    question: "Em que ano o produto foi lanÃƒÂ§ado?"
    tags: [factual, numbers]
  - id: abstain_01
    question: "Qual ÃƒÂ© o preÃƒÂ§o?"
    expected: ""   # agente deve dizer que nÃƒÂ£o encontrou
    tags: [abstain]
```

---

## CitaÃƒÂ§ÃƒÂµes e Verificador

- Cada chunk ÃƒÂ© numerado como `[Fonte N]` no contexto enviado ao LLM.
- O contexto inclui o **texto completo** do chunk (atÃƒÂ© `CONTEXT_MAX_CHARS` caracteres), nÃƒÂ£o apenas um snippet curto.
- O LLM ÃƒÂ© instruÃƒÂ­do a referenciar `[Fonte N]` na resposta.
- **Score threshold**: chunks com score abaixo de `MIN_RELEVANCE_SCORE` sÃƒÂ£o descartados.
- **MMR (Max Marginal Relevance)**: modo padrÃƒÂ£o Ã¢â‚¬â€ prioriza diversidade entre os chunks.
- **Hybrid search**: BM25 lexical + vector semantic, fusÃƒÂ£o via Reciprocal Rank Fusion (RRF).
- **Multi-query**: reescreve a query em N variaÃƒÂ§ÃƒÂµes usando o LLM para aumentar recall.
- **Reranking**: rescore dos chunks via bag-of-words (`local`) ou LLM (`llm`).
- **Stable IDs**: chunk_id = SHA-256(file_name + index + text), permitindo ingestÃƒÂ£o incremental.
- **Evidence snippets**: a seÃƒÂ§ÃƒÂ£o Fontes mostra o trecho mais relevante (nÃƒÂ£o apenas o inÃƒÂ­cio).
- `verify_grounding` conta citaÃƒÂ§ÃƒÂµes, detecta afirmaÃƒÂ§ÃƒÂµes factuais e **citaÃƒÂ§ÃƒÂµes fantasmas** (`[Fonte 9]` com apenas 2 chunks Ã¢â€ â€™ falha).
- Se falhar: incrementa `top_k` e reexecuta retrieval (atÃƒÂ© `MAX_RETRIES`).
- Se exceder retries: adiciona disclaimer de confianÃƒÂ§a baixa.
- Resposta final inclui seÃƒÂ§ÃƒÂ£o **Fontes:** com arquivo, pÃƒÂ¡gina, chunk_id e evidence snippet.

---

## Comandos CLI

### IngestÃƒÂ£o

```bash
# Indexar toda a pasta docs/
python -m docops ingest --path docs/

# Indexar um arquivo especÃƒÂ­fico
python -m docops ingest --file docs/manual.pdf

# Com chunk size personalizado
python -m docops ingest --path docs/ --chunk-size 600 --chunk-overlap 100
```

### Chat

```bash
# Iniciar chat interativo com seus documentos
python -m docops chat
```

### Listar documentos indexados

```bash
python -m docops list-docs
```

### Resumo de documento

```bash
python -m docops summarize --doc manual.pdf
python -m docops summarize --doc manual.pdf --save   # salva em artifacts/
```

### ComparaÃƒÂ§ÃƒÂ£o de documentos

```bash
python -m docops compare --doc1 v1.pdf --doc2 v2.pdf
python -m docops compare --doc1 v1.pdf --doc2 v2.pdf --save
```

### GeraÃƒÂ§ÃƒÂ£o de artefatos

```bash
python -m docops artifact --type study_plan --topic "Redes Neurais"
python -m docops artifact --type checklist --topic "Deploy em produÃƒÂ§ÃƒÂ£o" --output deploy_checklist.md
```

### Evaluation

```bash
# Rodar suite demo em modo mock (sem chamadas ÃƒÂ  API)
python -m docops.eval --suite demo --mock

# Rodar com retrieval hÃƒÂ­brido e reranking
python -m docops.eval --suite demo --retrieval hybrid --rerank on

# Especificar arquivo de saÃƒÂ­da
python -m docops.eval --suite demo --out artifacts/eval_demo.json

# Ver todos os flags
python -m docops.eval --help
```

---

## Executando os Testes

```bash
# Com o venv ativado
pytest

# Ou explicitamente via Python 3.11
/c/vscode/DocOps_Agent/.venv/Scripts/python.exe -m pytest tests/ -v
```

Os testes de Chroma (`test_chroma_ingest.py`) usam `FakeEmbeddings` determinÃƒÂ­sticos Ã¢â‚¬â€ nenhuma chamada ÃƒÂ  API Gemini ÃƒÂ© feita.

---

## Autenticação

### Configuração rápida

```bash
# 1. Gere um JWT_SECRET_KEY seguro
python -c "import secrets; print(secrets.token_hex(32))"

# 2. Adicione ao .env
JWT_SECRET_KEY=<valor gerado acima>
```

### Banco de dados

Por padrão, o banco é um arquivo SQLite em `./data/app.db`. As tabelas são criadas automaticamente no startup — sem necessidade de rodar migrações em desenvolvimento.

| Variável | Padrão | Descrição |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/app.db` | URL de conexão SQLAlchemy |
| `JWT_SECRET_KEY` | **(obrigatório)** | Segredo para assinar tokens JWT |
| `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` | `60` | Validade do access token (minutos) |
| `INGEST_ALLOWED_DIRS` | `DOCS_DIR` | Diretórios permitidos para ingest por path |

### Migração SQLite → PostgreSQL

Quando estiver pronto para produção:

```bash
# 1. Instale o driver
pip install psycopg2-binary

# 2. Configure o .env
DATABASE_URL=postgresql+psycopg2://usuario:senha@localhost:5432/docops

# 3. Reinicie o servidor — as tabelas são criadas automaticamente
python -m uvicorn docops.api.app:app
```

> **Nota:** O projeto usa SQLAlchemy 2.x, então a troca de banco é apenas mudança de `DATABASE_URL`. Nenhum código ORM precisa ser alterado.

### Rotas da API de auth

| Método | Rota | Autenticação | Descrição |
|---|---|---|---|
| `POST` | `/api/auth/register` | Pública | Cadastra usuário (nome, email, senha ≥8 chars) |
| `POST` | `/api/auth/login` | Pública | Retorna `access_token` JWT |
| `GET` | `/api/auth/me` | Bearer token | Dados do usuário logado |

Todas as outras rotas (`/api/docs`, `/api/chat`, `/api/ingest`, etc.) exigem `Authorization: Bearer <token>`.

### Roadmap de segurança (MVP vs Produção)

> O MVP usa JWT em `localStorage` por simplicidade. Para produção, recomendamos:

| Item | MVP | Produção (futuro) |
|---|---|---|
| Token storage | `localStorage` | Cookie `httpOnly` + CSRF token |
| Refresh token | Não | Sim (token rotation) |
| Rate limiting | Não | Sim (ex: slowapi) |
| HTTPS | Responsabilidade do infra | Obrigatório |
| Senha mínima | 8 caracteres | zxcvbn score + regras de complexidade |

---

## Roadmap

- [x] Interface web (FastAPI + React)
- [x] Multi-query retrieval
- [x] Reranking (local + LLM)
- [x] Hybrid search (BM25 + vector)
- [x] Stable IDs + incremental ingest
- [x] Citation improvements (evidence snippets)
- [x] Better verifier (phantom citations)
- [x] Structured chunking (MD/TXT heading-aware)
- [x] Semantic grounding verifier (claimÃ¢â€ â€™evidence)
- [x] Eval harness with YAML suites and JSON reports
- [ ] Suporte a DOCX e HTML
- [ ] Modo de comparaÃƒÂ§ÃƒÂ£o multi-documento expandido
- [ ] Cache semÃƒÂ¢ntico de queries repetidas
- [ ] ExportaÃƒÂ§ÃƒÂ£o de sessÃƒÂ£o de chat
