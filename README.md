# DocOps Agent

Assistente RAG (Retrieval-Augmented Generation) para documentos, com sumarização profunda, comparação, flashcards, plano de estudos, tarefas, calendário e muito mais.

---
# como rodar

Terminal 1 — API (backend):


cd c:/dev/DocOps_Agent
.venv/Scripts/uvicorn docops.api.app:app --reload --port 8000
Terminal 2 — Web (frontend):


cd c:/dev/DocOps_Agent/web
npm run dev


## Stack

### Backend
| Camada | Tecnologia |
|--------|-----------|
| Framework web | FastAPI + Uvicorn |
| Agente/grafo | LangGraph |
| LLM | Google Gemini (via `langchain-google-genai`) |
| Banco vetorial | ChromaDB |
| Busca léxica | BM25 (`rank-bm25`) |
| ORM / banco relacional | SQLAlchemy + SQLite (dev) / PostgreSQL (prod) |
| Autenticação | JWT (`PyJWT` + `bcrypt`) |
| Leitura de documentos | pypdf, openpyxl, xlrd, odfpy, beautifulsoup4 |
| CLI | Typer + Rich |
| Testes | pytest + pytest-asyncio |

### Frontend
| Camada | Tecnologia |
|--------|-----------|
| Framework | React 19 + TypeScript |
| Build | Vite 7 |
| Roteamento | React Router 7 |
| UI | Tailwind CSS 4 + Radix UI |
| Animações | Framer Motion 12 |
| 3D | React Three Fiber + Three.js |
| HTTP | Axios + TanStack Query |
| Testes E2E | Playwright |

---

## Arquitetura

```
┌─────────────────────────────────────────┐
│              Frontend (React)           │
│  Landing · Chat · Docs · Ingest · ...   │
└──────────────────┬──────────────────────┘
                   │ HTTP / REST (HTTPS via VITE_API_URL)
┌──────────────────▼──────────────────────┐
│            FastAPI  /api/*              │
│  auth · chat · ingest · summarize · ... │
└──────┬───────────────────┬──────────────┘
       │                   │
┌──────▼──────┐   ┌────────▼────────────────────────┐
│  SQLite /   │   │         LangGraph Agent          │
│ PostgreSQL  │   │  classify → retrieve → synthesize│
│  (users,    │   │       → verify_grounding         │
│  docs, etc) │   └────────┬────────────────────────┘
└─────────────┘            │
                  ┌────────▼────────────────────┐
                  │        RAG Pipeline          │
                  │  ChromaDB (vetores por user) │
                  │  BM25 (léxico por user)      │
                  │  Hybrid search + reranking   │
                  └─────────────────────────────┘
```

### Fluxo do Grafo LangGraph (QA / brief summary)

```
classify_intent → retrieve → synthesize → verify_grounding
                                                ↓
                                   [retry?] retry_retrieve
                                                ↓
                                           finalize → END
```

### Pipeline Deep Summary (`docops/summarize/pipeline.py`)

```
collect_ordered_chunks
      ↓
clean_chunks            (NFC, null bytes, controles, PUA, ligaduras)
      ↓
group_chunks            (section-based ≥70% ou window-based fallback)
      ↓
summarize_groups        (1 chamada LLM por grupo, max 6 grupos)
      ↓
consolidate_summaries   (1 chamada LLM → visão global)
      ↓
select_citation_anchors (1 chunk/grupo + fill uniforme, max 12)
      ↓
finalize_deep_summary   (1 chamada LLM com citation_anchors)
      ↓
validate_summary_citations  (remove [Fonte N] fantasmas)
      ↓
validate_summary_grounding  (overlap de tokens por bloco)
      ↓
clean_summary_output
      ↓
build_anchor_sources_section
```

---

## Estrutura de Diretórios

```
DocOps_Agent/
├── docops/
│   ├── api/
│   │   ├── app.py              # FastAPI factory + routers
│   │   ├── routes/             # 16 módulos de rota
│   │   └── schemas.py          # Todos os modelos Pydantic
│   ├── auth/
│   │   ├── dependencies.py     # get_current_user (FastAPI Depends)
│   │   └── security.py         # JWT encode/decode, hash de senha
│   ├── config.py               # Singleton config (100+ propriedades)
│   ├── db/
│   │   ├── database.py         # Engine, session, init_db()
│   │   ├── models.py           # 14 modelos ORM
│   │   └── crud.py             # Operações de banco
│   ├── graph/
│   │   ├── graph.py            # build_graph() + run()
│   │   ├── nodes.py            # 6 funções de nó
│   │   └── state.py            # AgentState TypedDict
│   ├── grounding/
│   │   ├── claims.py           # Extração de claims factuais
│   │   └── support.py          # Verificação SUPPORTED/UNCLEAR
│   ├── ingestion/
│   │   ├── indexer.py          # Persiste chunks no Chroma + BM25
│   │   ├── loaders.py          # PDF/MD/TXT → Documents
│   │   ├── md_splitter.py      # Chunking por headings ATX
│   │   ├── splitter.py         # Dispatcher por file_type
│   │   └── txt_splitter.py     # Chunking heurístico TXT
│   ├── rag/
│   │   ├── citations.py        # build_context_block, build_sources_section
│   │   ├── hybrid.py           # Busca híbrida (vetor + BM25)
│   │   ├── prompts.py          # 15+ templates de prompt
│   │   ├── retriever.py        # retrieve(), retrieve_for_doc()
│   │   └── verifier.py         # verify_grounding (heurística)
│   ├── services/
│   │   └── ownership.py        # require_user_document / require_user_artifact
│   ├── storage/paths.py        # Caminhos de coleção Chroma por usuário
│   ├── summarize/
│   │   ├── pipeline.py         # run_deep_summary() — pipeline multi-etapas
│   │   └── text_cleaner.py     # Limpeza de chunks e output LLM
│   └── tools/doc_tools.py      # tool_search_docs, tool_list_docs, tool_write_artifact
├── eval/                       # Harness de avaliação + suites YAML
├── tests/                      # pytest
├── web/                        # Frontend React
│   └── src/
│       ├── api/client.ts       # Cliente HTTP (axios)
│       ├── hooks/              # useAI, useScrollProgress, useDynamicDelay, ...
│       ├── lib/stagger.ts      # getDynamicDelay (stagger position-aware)
│       ├── pages/              # 14 páginas React
│       └── components/         # Layout, Sidebar, UI primitives
├── vercel.json                 # Rewrites Vercel (SPA fallback)
├── docker-compose.yml
├── docker/
│   ├── backend/Dockerfile
│   ├── frontend/Dockerfile
│   ├── production/Dockerfile
│   └── nginx.conf
├── pyproject.toml
└── .env                        # Não commitado
```

---

## Modelos de Banco de Dados

| Tabela | Descrição |
|--------|-----------|
| `users` | Usuários com hash de senha, email único |
| `documents` | Registros de documentos indexados por usuário |
| `artifacts` | Artefatos gerados (resumos, comparações, flashcards) |
| `reminders` | Lembretes com data/hora de início e fim |
| `schedules` | Grade horária semanal (dia da semana + horário) |
| `notes` | Notas pessoais (pinned, Markdown) |
| `tasks` | Tarefas com status, prioridade, prazo |
| `task_checklist_items` | Itens de checklist por tarefa |
| `task_activity_logs` | Log de atividade por tarefa |
| `flashcard_decks` | Baralhos de flashcards |
| `flashcard_items` | Cards individuais com algoritmo de repetição espaçada |
| `study_plans` | Planos de estudo vinculados a documentos |
| `daily_questions` | Pergunta diária gerada por IA |
| `reading_status` | Status de leitura por documento (to_read / reading / done) |

---

## Endpoints da API

**Base URL:** `/api`

### Autenticação (público)
```
POST   /api/register
POST   /api/login
GET    /api/me
GET    /api/health
```

### Documentos (autenticado)
```
GET    /api/docs
DELETE /api/docs/{doc_id}
GET    /api/docs/reading-status
PATCH  /api/docs/{doc_id}/reading-status
```

### Ingestão (autenticado)
```
POST   /api/ingest          (path local)
POST   /api/ingest/upload   (upload de arquivo)
POST   /api/ingest/url      (URL / YouTube)
POST   /api/ingest/clip     (texto de clipboard)
POST   /api/ingest/photo    (OCR de imagem)
```

### Chat & Resumo (autenticado)
```
POST   /api/chat
POST   /api/compare
POST   /api/summarize       (brief | deep)
POST   /api/summarize/async
```

### Artefatos (autenticado)
```
POST   /api/artifact
POST   /api/artifact/async
GET    /api/artifacts
GET    /api/artifacts/{filename}
GET    /api/artifacts/{filename}/pdf
DELETE /api/artifacts/{filename}
```

### Calendário & Lembretes (autenticado)
```
GET/POST/PUT/DELETE  /api/reminders
GET/POST/PUT/DELETE  /api/schedules
GET                  /api/overview
```

### Notas (autenticado)
```
GET/POST/PUT/DELETE  /api/notes
```

### Tarefas (autenticado)
```
GET/POST/PUT/DELETE  /api/tasks
GET/POST/PUT/DELETE  /api/tasks/{id}/checklist
GET/POST/DELETE      /api/tasks/{id}/activities
```

### Flashcards (autenticado)
```
GET    /api/flashcards
POST   /api/flashcards/generate
GET    /api/flashcards/{deck_id}
POST   /api/flashcards/review
POST   /api/flashcards/card/{card_id}/evaluate
PUT    /api/flashcards/card/{card_id}/difficulty
DELETE /api/flashcards/{deck_id}
```

### Pipeline / Estudo (autenticado)
```
POST   /api/studyplan
POST   /api/pipeline/study-plan
GET    /api/pipeline/study-plans
DELETE /api/pipeline/study-plans/{plan_id}
GET    /api/pipeline/daily-question
POST   /api/pipeline/digest
POST   /api/pipeline/extract-tasks
POST   /api/pipeline/gap-analysis
POST   /api/pipeline/evaluate-answer
GET    /api/briefing
GET    /api/jobs/{job_id}
```

---

## Variáveis de Ambiente

### Backend (`.env`)

#### Obrigatórias
```env
GEMINI_API_KEY=          # Chave da API Google Gemini
JWT_SECRET_KEY=          # Segredo JWT (gerar: python -c "import secrets; print(secrets.token_hex(32))")
```

#### Banco de Dados
```env
DATABASE_URL=sqlite:///./data/app.db   # SQLite (dev) ou postgresql://... (prod)
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRES_MINUTES=60
```

#### Caminhos
```env
CHROMA_DIR=./data/chroma
DOCS_DIR=./docs
UPLOADS_DIR=./uploads
ARTIFACTS_DIR=./artifacts
BM25_DIR=./data/bm25
```

#### RAG / Retrieval
```env
TOP_K=6
CHUNK_SIZE=900
CHUNK_OVERLAP=150
RETRIEVAL_MODE=mmr          # mmr | similarity | hybrid
MMR_LAMBDA=0.5
CONTEXT_MAX_CHARS=1500
MULTI_QUERY=false
RERANKER=none               # none | local | llm
HYBRID_ALPHA=0.5
```

#### Modelos LLM
```env
GEMINI_MODEL=gemini-2.5-flash
GEMINI_MODEL_ROUTER_ENABLED=true
GEMINI_MODEL_COMPLEX=gemini-3-flash-preview
GEMINI_MODEL_CHEAP=gemini-3.1-flash-lite-preview
GEMINI_MODEL_QA_SIMPLE=gemini-2.5-flash
```

Roteamento determinístico de modelos (resumo):
- `GEMINI_MODEL`: fallback base quando o router está desligado (`GEMINI_MODEL_ROUTER_ENABLED=false`) ou quando a rota não é reconhecida.
- `GEMINI_MODEL_COMPLEX` (rota `complex`): síntese pesada do deep summary (consolidação/finalização/re-synthesis) e intents de maior complexidade no grafo (`summary` deep, `comparison`, `study_plan`, `checklist`).
- `GEMINI_MODEL_CHEAP` (rota `cheap`): passos auxiliares e baratos (classificação de intent, rewrites, rerank LLM, validações/grounding semântico, passes leves) e `summary` brief no grafo.
- `GEMINI_MODEL_QA_SIMPLE` (rota `qa_simple`): resposta de Q&A direta e reparo de grounding no fluxo de chat.

#### Grounding & Verificação
```env
SEMANTIC_GROUNDING_ENABLED=true
GROUNDED_VERIFIER_MODE=llm       # heuristic | llm | hybrid
MIN_SUPPORT_RATE=0.5
MAX_RETRIES=2
MIN_CITATIONS=2
```

#### Ingestão
```env
STRUCTURED_CHUNKING=true
INGEST_INCREMENTAL=false
```

#### Pipeline Deep Summary
```env
SUMMARY_DEEP_PROFILE=balanced     # fast | balanced | model_first | model_first_plus | model_first_plus_max | strict
SUMMARY_GROUP_SIZE=8
SUMMARY_MAX_GROUPS=6
SUMMARY_SECTION_THRESHOLD=0.70
SUMMARY_MAX_SOURCES=12
SUMMARY_GROUNDING_THRESHOLD=0.20
SUMMARY_GROUNDING_REPAIR=false
```

Perfis de execução do deep summary:
- `fast`: menor latência, desativa passes corretivos caros.
- `balanced` (padrão atual): equilíbrio entre qualidade e custo, com pipeline completo e sem fail-closed estrito.
- `model_first`: caminho simplificado para modelos mais fortes (menos orquestração corretiva em cascata).
- `model_first_plus`: model_first com passe de de-overreach habilitado.
- `model_first_plus_max`: model_first_plus + micro-backfill para tópicos obrigatórios faltantes.
- `strict`: mesmo fluxo com gate final fail-closed (pode retornar erro 422 quando a qualidade mínima não for atingida).

#### Servidor
```env
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
LOG_LEVEL=INFO
```

### Frontend (`web/.env.local`)
```env
VITE_API_URL=http://localhost:8000
```
> Em produção no Vercel, configure `VITE_API_URL` com a URL pública do backend.

---

## Como Rodar Localmente

### Pré-requisitos
- Python 3.11+
- Node.js 20+
- Chave da API Google Gemini ([aistudio.google.com](https://aistudio.google.com))

### 1. Clonar e configurar

```bash
git clone https://github.com/rouggerxavier/DocOps_Agent.git
cd DocOps_Agent
```

### 2. Backend

```bash
# Criar e ativar ambiente virtual
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate           # Windows

# Instalar dependências
pip install -e ".[dev]"

# Configurar variáveis de ambiente
cp .env.example .env
# Editar .env: GEMINI_API_KEY e JWT_SECRET_KEY

# Iniciar servidor (cria banco automaticamente na primeira execução)
python -m uvicorn docops.api.app:app --host 0.0.0.0 --port 8000 --reload
```

API disponível em: `http://localhost:8000`
Documentação interativa: `http://localhost:8000/api/docs-ui`

### 3. Frontend

```bash
cd web
npm install

# Configurar (opcional — padrão já aponta para localhost:8000)
echo "VITE_API_URL=http://localhost:8000" > .env.local

npm run dev
```

Frontend disponível em: `http://localhost:5173`

### 4. Docker Compose (stack completa)

```bash
docker-compose up --build
```

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`

---

## Deploy em Produção

### Frontend — Vercel

1. Conecte o repositório GitHub no Vercel
2. Configure:
   - **Root Directory:** *(deixe em branco — usa `vercel.json` na raiz)*
   - **Build Command:** `cd web && npm install && npm run build`
   - **Output Directory:** `web/dist`
3. Configure a variável de ambiente `VITE_API_URL` no projeto Vercel apontando para o backend (ex.: `https://api.seudominio.com`).
4. O `vercel.json` mantém apenas o fallback SPA para `index.html`.

### Backend — Oracle Cloud (ou qualquer VM)

```bash
# No servidor
git clone https://github.com/rouggerxavier/DocOps_Agent.git
cd DocOps_Agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configurar .env com GEMINI_API_KEY, JWT_SECRET_KEY, DATABASE_URL

# Subir com nohup (simples)
nohup uvicorn docops.api.app:app --host 0.0.0.0 --port 8000 > ~/docops.log 2>&1 &

# Ou configurar como serviço systemd (recomendado para produção)
```

**Security List Oracle:** libere a porta 8000 (TCP) nas regras de ingress.

### CI/CD — GitHub Actions

O workflow `.github/workflows/deploy-oracle.yml` faz deploy automático no Oracle a cada push em `main` que altere arquivos do backend. Ele:
1. Conecta via SSH no servidor Oracle
2. Faz `git pull`
3. Reinstala dependências
4. Reinicia o serviço systemd `docops`
5. Verifica saúde via `/api/health`

---

## Testes

```bash
# Backend
pytest tests/

# Frontend E2E
cd web
npx playwright test
```

---

## Páginas do Frontend

| Página | Rota | Descrição |
|--------|------|-----------|
| Landing | `/` | Página pública com demo de IA |
| Login | `/login` | Autenticação |
| Register | `/register` | Criação de conta |
| Dashboard | `/dashboard` | Painel principal |
| Chat | `/chat` | QA sobre documentos |
| Documentos | `/docs` | Lista + resumo + comparação |
| Inserção | `/ingest` | Upload de arquivos (PDF, MD, TXT, CSV, XLSX) |
| Artefatos | `/artifacts` | Visualizar e baixar artefatos gerados |
| Notas | `/notes` | Notas pessoais em Markdown |
| Tarefas | `/tasks` | Gerenciador de tarefas com checklist |
| Calendário | `/schedule` | Lembretes + grade semanal |
| Flashcards | `/flashcards` | Baralhos com repetição espaçada |
| Plano de Estudos | `/study-plan` | Criação de planos vinculados a documentos |
| Kanban de Leitura | `/reading` | Kanban: to_read → reading → done |

---

## Convenções do Projeto

- **Config:** sempre `from docops.config import config` — nunca `os.getenv()` diretamente
- **Logger:** `from docops.logging import get_logger; logger = get_logger("docops.módulo")`
- **Imports pesados** (LLM, vectorstore): lazy, dentro das funções — evita lentidão no import
- **Multi-tenancy:** `user_id` sempre passado para `retrieve`, `retrieve_for_doc`, `get_vectorstore_for_user`
- **Ownership:** sempre chamar `require_user_document` antes de acessar chunks de um usuário
- **Testes:** pytest com `monkeypatch` ou `unittest.mock`
