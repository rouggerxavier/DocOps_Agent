# DocOps Onboarding — Spec

**Status:** Draft v1 — aguardando revisão antes de implementar
**Branch:** `feat/onboarding-tour`
**Autoria:** Rougger + Claude
**Data:** 2026-04-24

---

## 0. Contexto e problema

O produto hoje tem um placeholder de "Primeiros passos" no Dashboard (ver [Dashboard.tsx:190](../../web/src/pages/Dashboard.tsx#L190)) com 3 itens estáticos que não detectam progresso, não somem quando concluídos e não explicam as features reais. Qualquer usuário novo cai direto numa UI com muitas páginas (Dashboard, Chat, Docs, Ingest, Artefatos, Calendário, Notas, Tarefas, Flashcards, Plano de Estudos, Kanban, Configurações) sem entender (a) por onde começar, (b) o que cada seção faz, (c) como as seções se conectam, (d) o que é grátis vs premium.

## 1. Objetivos

1. **Ativar o novo usuário** nos primeiros 2 minutos: ele precisa sair do registro sabendo (1) o que o produto faz, (2) qual o fluxo mínimo pra ter valor (inserir doc → conversar → salvar artefato), (3) onde cada área mora.
2. **Educar progressivamente** sobre as demais features (memória, flashcards, plano de estudos, etc.) sem bombardear no primeiro login.
3. **Criar ganchos entre seções**: quando o usuário entra numa tela pela primeira vez, um intro curto explica aquela área e aponta para a próxima etapa natural do fluxo.
4. **Ser 100% pulável**: skip total, skip por seção, e possibilidade de re-abrir pelo menu de Configurações.
5. **Medir funil**: instrumentar completion/skip por etapa pra saber onde o onboarding perde gente.

### Não-objetivos (explicitamente fora do escopo desta spec)
- Tour guiado com animação 3D ou mascote.
- Onboarding diferente por persona (estudante, profissional etc.) — v2.
- Tradução para outros idiomas — produto é PT-BR.
- Tutorial in-app para features que ainda não existem.

## 2. Princípios de UX

| Princípio | Aplicação prática |
|---|---|
| **Progresso visível** | Checklist persistente mostrando X/Y concluído. |
| **Opt-out fácil** | Botão "Pular tudo" sempre visível; cada intro seccional tem "Dispensar". |
| **Detecção automática** | Concluir um passo é uma ação real (ex.: primeiro upload), não um clique em "feito". |
| **Não bloqueia** | Nenhuma etapa impede o usuário de usar o produto. Modais são dispensáveis. |
| **Contextual** | Intro de seção aparece ao entrar na página, não em overlay global. |
| **Retomável** | Re-abrir o tutorial em Configurações restaura o checklist. |

## 3. Arquitetura

### 3.1 Visão em camadas

```
┌─────────────────────────────────────────────────────────────────┐
│ React components                                                 │
│   ├── WelcomeModal (1ª login)                                    │
│   ├── OnboardingChecklist (card lateral/flutuante persistente)  │
│   ├── SectionIntro (card no topo de cada page na 1ª visita)      │
│   └── HotspotTour (tooltip sequencial opcional por seção)       │
├─────────────────────────────────────────────────────────────────┤
│ OnboardingProvider (context)                                     │
│   ├── fetch /api/onboarding/state                                │
│   ├── useOnboarding() → { state, completeStep, skipSection, …}  │
│   └── Auto-progressão via hooks nas ações do app                 │
├─────────────────────────────────────────────────────────────────┤
│ API FastAPI                                                      │
│   ├── GET  /api/onboarding/state                                 │
│   ├── POST /api/onboarding/events                                │
│   ├── POST /api/onboarding/reset                                 │
│   └── GET  /api/onboarding/catalog (opcional, ver §5.4)         │
├─────────────────────────────────────────────────────────────────┤
│ Persistência (Postgres)                                          │
│   └── user_onboarding_state (1 linha por user)                   │
│       + user_onboarding_events (append-only, telemetria)         │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Feature flag e entitlement

- Flag backend: `onboarding_enabled` (via `FEATURE_FLAGS`). Default **true**. Permite desligar em produção se algo der errado.
- **Não** é gated por entitlement — onboarding é para todo usuário, inclusive free. Mas **passos específicos** referentes a features premium são marcados com `premium: true` no catálogo e renderizam CTA de upgrade em vez de "executar agora".

### 3.3 Versionamento do catálogo

O catálogo de passos tem campo `schema_version` (int). Se bumpar (ex.: nova seção), o front compara com a versão salva no state do user e oferece "Novidade: [X] etapas novas foram adicionadas, quer ver?". Não ressetta progresso antigo.

## 4. Modelo de dados (backend)

### 4.1 Tabela `user_onboarding_state`

Uma linha por usuário, criada lazy no primeiro `GET /state`.

| Coluna | Tipo | Notas |
|---|---|---|
| `user_id` | UUID PK, FK users.id | |
| `schema_version` | int, NOT NULL, default 1 | Versão do catálogo que o usuário viu pela última vez. |
| `welcome_seen_at` | timestamptz NULL | Modal de boas-vindas foi exibido/fechado. |
| `tour_started_at` | timestamptz NULL | Usuário iniciou o tour pela 1ª vez (clicou em "Começar" no welcome). |
| `tour_completed_at` | timestamptz NULL | Todos os passos não-skipados foram completados. |
| `tour_skipped_at` | timestamptz NULL | Usuário pulou tudo. Quando preenchido, UI esconde elementos de onboarding até reset. |
| `step_completions` | JSONB, default `{}` | `{ "ingest.first_upload": "2026-04-24T...", ... }` |
| `section_skips` | JSONB, default `{}` | `{ "flashcards": "2026-04-24T..." }` seções que o usuário dispensou. |
| `last_step_seen` | varchar(64) NULL | Último `step_id` que o usuário abriu (pra retomar na mesma etapa). |
| `created_at` | timestamptz, default now() | |
| `updated_at` | timestamptz, default now() | |

Índices: PK em `user_id`.

### 4.2 Tabela `user_onboarding_events` (telemetria)

Append-only. Útil para funil e análise retrospectiva.

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID, FK users.id | |
| `event_type` | varchar(48) | `welcome_shown`, `tour_started`, `step_seen`, `step_completed`, `section_skipped`, `tour_skipped`, `tour_completed`, `tour_reset`, `upgrade_intent_from_onboarding`. |
| `step_id` | varchar(64) NULL | ID do passo quando aplicável. |
| `section_id` | varchar(32) NULL | Seção (dashboard, ingest, chat, ...). |
| `metadata` | JSONB NULL | ex.: `{ "trigger": "auto"/"manual", "premium_cta": "templates" }` |
| `occurred_at` | timestamptz, default now() | |

Índices: `(user_id, occurred_at)`, `(event_type, occurred_at)`.

### 4.3 Migration

Alembic revision `0007_onboarding_state_and_events`, `down_revision = "0006_user_admin_flag"`.

Boolean/json defaults usar sintaxe compatível com Postgres (lição aprendida da 0006: `sa.text("false")` e `sa.text("'{}'::jsonb")`).

## 5. Contrato de API

Todos os endpoints abaixo exigem auth (Bearer token), prefixo `/api`, mesmo padrão dos demais routers.

### 5.1 `GET /api/onboarding/state`

Retorna o estado consolidado do usuário + catálogo hidratado com progresso.

**Response 200:**
```json
{
  "schema_version": 1,
  "tour": {
    "welcome_seen": false,
    "started": false,
    "completed": false,
    "skipped": false,
    "progress": { "completed": 0, "total": 12 }
  },
  "sections": [
    {
      "id": "dashboard",
      "title": "Dashboard",
      "icon": "layout",
      "route": "/dashboard",
      "skipped": false,
      "steps": [
        {
          "id": "dashboard.explore",
          "title": "Entenda seu painel",
          "description": "Visão geral das suas conversas, documentos e artefatos.",
          "premium": false,
          "completion_mode": "manual",
          "completed_at": null,
          "next_hint": { "section": "ingest", "step": "ingest.first_upload" }
        }
      ]
    }
  ],
  "last_step_seen": null
}
```

Comportamento:
- Se não existe linha em `user_onboarding_state`, cria com defaults e retorna.
- Se `schema_version` salva < atual, retorna campo `schema_upgrade_available: true` no response.
- `sections` sempre inclui **todas** as seções definidas no catálogo, mesmo as com `skipped=true` (o front decide renderizar ou não).

### 5.2 `POST /api/onboarding/events`

Mutação única pra todos os eventos. Request idempotente por `(user_id, event_type, step_id, section_id)` em `step_completed`, `step_seen`, `section_skipped`, `welcome_shown` (reenvios não duplicam timestamp).

**Request:**
```json
{
  "event_type": "step_completed",
  "step_id": "ingest.first_upload",
  "section_id": "ingest",
  "metadata": { "trigger": "auto" }
}
```

**Response 200:**
```json
{ "state": { /* mesmo shape de GET /state */ } }
```

**Tipos de evento aceitos:**

| `event_type` | Efeito em `user_onboarding_state` | Quem dispara |
|---|---|---|
| `welcome_shown` | `welcome_seen_at = now()` (se null) | Front, ao fechar modal |
| `tour_started` | `tour_started_at = now()` (se null) | Front, ao clicar "Começar" |
| `step_seen` | `last_step_seen = step_id` | Front, ao abrir um passo |
| `step_completed` | `step_completions[step_id] = now()`; se todos concluídos, `tour_completed_at = now()` | Front (manual) ou hooks auto-progressão |
| `section_skipped` | `section_skips[section_id] = now()` | Front, ao clicar "Dispensar seção" |
| `tour_skipped` | `tour_skipped_at = now()` | Front, ao clicar "Pular tudo" |
| `upgrade_intent_from_onboarding` | (só telemetria, sem efeito em state) | Front, ao clicar CTA de upgrade em passo premium |
| `tour_reset` | Limpa: `tour_skipped_at`, `section_skips`, `welcome_seen_at`, `last_step_seen`. **Preserva** `step_completions`. Usado ao re-abrir tutorial. | Front, ao clicar "Rever tutorial" em Configurações |

**Regras:**
- Validar `step_id` e `section_id` contra catálogo; rejeitar desconhecidos com 400.
- Todo evento grava linha em `user_onboarding_events`.
- `tour_completed_at` é derivado — backend calcula se todos os passos não dispensados estão concluídos após cada `step_completed`.

### 5.3 `POST /api/onboarding/reset`

Zera tudo (inclusive `step_completions`). Útil para QA ou decisão do produto. Só admin ou conta self-service?

**Decisão:** self-service. `POST /api/onboarding/reset` do próprio user zera o progresso dele. Admin pode usar endpoint separado `/api/admin/...` (fora desta spec).

**Response:** mesmo shape de `GET /state`, já resetado.

### 5.4 Catálogo: estático ou endpoint?

**Decisão:** catálogo é estático no backend (Python dict em `docops/onboarding/catalog.py`), embutido na resposta de `GET /state`. Não tem endpoint separado. Motivo: evita 2 requests no primeiro load; catálogo raramente muda (versão via `schema_version`).

## 6. Catálogo de conteúdo

Estrutura em **12 passos** distribuídos em **8 seções**. Passos marcados com 🔒 são premium (exibem CTA de upgrade no free tier).

### 6.1 Welcome (pre-tour)

Modal de 3 frames exibido **uma vez** após primeiro login:

1. **"Oi, eu sou o DocOps Agent."** — 1 frase explicando a proposta: "seu assistente de estudos com IA que lê seus documentos e responde com citação".
2. **"Como funciono em 30s"** — ilustração das 3 etapas (inserir → conversar → salvar) com bullets curtos.
3. **"Vamos começar?"** — dois botões: "Quero um tour rápido" (→ tour_started) ou "Explorar sozinho" (→ welcome_shown only).

### 6.2 Seção **dashboard** `/dashboard`

| Step ID | Título | Descrição | Conclusão | Gancho |
|---|---|---|---|---|
| `dashboard.explore` | Entenda seu painel | Onde você vê suas últimas conversas, documentos importados, artefatos criados e recomendações. | manual (ler e fechar) | → `ingest.first_upload` |

### 6.3 Seção **ingest** `/ingest`

Explica os **4 tipos de inserção** suportados (`/ingest`, `/ingest/upload`, `/ingest/clip`, `/ingest/photo`).

| Step ID | Título | Descrição | Conclusão | Gancho |
|---|---|---|---|---|
| `ingest.types_overview` | 4 formas de trazer conteúdo | Arquivo (PDF/MD/TXT), URL de artigo, foto (OCR) e clip compartilhado do celular. | manual | — |
| `ingest.first_upload` | Insira seu primeiro documento | Tutorial inline: "arraste um PDF aqui ou clique em escolher". | auto: `POST /api/ingest/upload` 200 | → `chat.first_question` |

### 6.4 Seção **chat** `/chat`

| Step ID | Título | Descrição | Conclusão | Gancho |
|---|---|---|---|---|
| `chat.first_question` | Faça sua primeira pergunta | Como o grounding funciona (responde a partir dos docs), modos (equilibrado/estrito), citações numeradas. | auto: `POST /api/chat` ou `/chat/stream` 200 | → `chat.grounding_modes` |
| `chat.grounding_modes` | Modos de resposta | Equilibrado vs Estrito: quando usar cada um, impacto na confiança. | manual | → `artifacts.first_save` |
| 🔒 `chat.memory` | Memória ativa (premium) | Explica personalização: tom, profundidade, rotina. Free vê "descubra no Pro" com CTA. | manual | — |

### 6.5 Seção **artifacts** `/artifacts`

| Step ID | Título | Descrição | Conclusão | Gancho |
|---|---|---|---|---|
| `artifacts.first_save` | Transforme chat em artefato | Salvar uma resposta como resumo, checklist ou nota estruturada. | auto: `POST /api/artifact/from-chat` OR `POST /api/artifact` 200 | → `docs.library` |
| 🔒 `artifacts.premium_templates` | Templates avançados | `exam_pack` e `deep_dossier` — pra provas e pesquisas profundas. Free vê teaser. | manual | — |

### 6.6 Seção **docs** `/docs`

| Step ID | Título | Descrição | Conclusão | Gancho |
|---|---|---|---|---|
| `docs.library` | Sua biblioteca | Lista completa dos documentos inseridos. Filtros, status de leitura, remoção. | manual | → `tasks_notes.quick_capture` |

### 6.7 Seção **productivity** (Notas + Tarefas + Calendário)

Agrupada por afinidade de uso.

| Step ID | Título | Descrição | Conclusão | Gancho |
|---|---|---|---|---|
| `productivity.notes_tasks` | Anote e organize | Notas rápidas, tarefas com checklist e calendário para lembretes/rotina. | manual | → `flashcards.generate_first` |

### 6.8 Seção **study** (Flashcards + Plano + Kanban)

| Step ID | Título | Descrição | Conclusão | Gancho |
|---|---|---|---|---|
| `study.flashcards` | Gere flashcards automáticos | A partir dos docs, cria decks com SRS (Spaced Repetition System). | auto: `POST /api/flashcards/generate` OR `generate-batch` 200 | → `study.plan` |
| `study.plan` | Plano de estudos | Cria um plano adaptado com gap analysis. | manual | → `study.kanban` |
| `study.kanban` | Kanban de leitura | Visualização em board pra organizar o que ler. | manual | — |

### 6.9 Seção **settings** `/settings`

| Step ID | Título | Descrição | Conclusão | Gancho |
|---|---|---|---|---|
| `settings.personalization` | Personalize respostas | Tom, profundidade, rigor. (Premium se `personalization_enabled`) | manual | — |

### 6.10 Resumo

| Seção | Passos | Passos premium |
|---|---|---|
| dashboard | 1 | 0 |
| ingest | 2 | 0 |
| chat | 3 | 1 |
| artifacts | 2 | 1 |
| docs | 1 | 0 |
| productivity | 1 | 0 |
| study | 3 | 0 |
| settings | 1 | 0 |
| **TOTAL** | **14** | **2** |

> Números podem ser ajustados na Fase 1 (content pass) depois que a implementação base estiver pronta.

## 7. Arquitetura frontend

### 7.1 Provider

`web/src/onboarding/OnboardingProvider.tsx`:

```tsx
const OnboardingProvider: FC = ({ children }) => {
  const { data, refetch } = useQuery(['onboarding', 'state'], fetchState)
  const mutate = useMutation(postEvent, { onSuccess: (res) => setData(res.state) })
  // ...
  return <OnboardingContext.Provider value={{ state, completeStep, skipSection, ...}}>{children}</OnboardingContext.Provider>
}
```

Montado dentro de `CapabilitiesProvider` em `App.tsx:88`, só pra rotas autenticadas.

### 7.2 Componentes

| Arquivo | Responsabilidade |
|---|---|
| `web/src/onboarding/OnboardingProvider.tsx` | Context + query + mutações. |
| `web/src/onboarding/useOnboarding.ts` | Hook público. |
| `web/src/onboarding/useStepAutoComplete.ts` | Hook utilitário: dispara `completeStep(id)` quando uma condição é satisfeita (usado nas pages). |
| `web/src/onboarding/WelcomeModal.tsx` | Modal inicial de 3 frames. |
| `web/src/onboarding/OnboardingChecklist.tsx` | Card persistente com progresso, refatorando o `OnboardingSteps` atual do Dashboard. |
| `web/src/onboarding/SectionIntro.tsx` | Card inline no topo de cada page na 1ª visita. Dispensável. |
| `web/src/onboarding/HotspotTour.tsx` | (Fase 5) Tour tooltip por seção, lazy-loaded. |
| `web/src/onboarding/catalog.ts` | Espelha o catálogo do backend (pra tipagem forte; fonte de verdade ainda é o backend). |

### 7.3 Detecção automática de conclusão (auto-progression)

Padrão: a page (ex.: `Ingest.tsx`) chama `useStepAutoComplete('ingest.first_upload', uploadSuccess)` que, quando `uploadSuccess` vira true, dispara `POST /events` com `trigger: "auto"`.

Hooks necessários por passo auto:

| Step ID | Trigger |
|---|---|
| `ingest.first_upload` | `useIngestUpload` mutation `onSuccess` |
| `chat.first_question` | Primeira resposta do `/chat` ou `/chat/stream` que não retorna erro |
| `artifacts.first_save` | `POST /artifact` ou `/artifact/from-chat` `onSuccess` |
| `study.flashcards` | `POST /flashcards/generate*` `onSuccess` |

### 7.4 Estratégia de "primeira visita" em cada seção

`SectionIntro` lê `state.sections[x].steps.filter(s => !s.completed_at && !section.skipped)` e, se houver ≥1 passo manual não concluído, mostra o card no topo da página com:
- Título + descrição do primeiro passo pendente
- Botão "Entendi" → `step_completed` com `trigger: "manual"`
- Botão "Pular esta seção" → `section_skipped`
- Link "Me mostra com tour" (Fase 5) → abre HotspotTour daquela seção

### 7.5 Re-abrir tour

Em `/settings`, adicionar card "Tutorial" com botões:
- **"Rever tutorial"** → `POST /events { tour_reset }` → abre welcome modal
- **"Resetar progresso completo"** → `POST /reset` (pede confirmação)

## 8. Plano de implementação por fases

Cada fase = 1 commit (ou PR pequeno) e deve deixar o código em estado funcional.

### Fase 1 — Backend scaffold
- [ ] Criar `docops/onboarding/catalog.py` com catálogo v1.
- [ ] Adicionar models em `docops/db/models.py`: `UserOnboardingState`, `UserOnboardingEvent`.
- [ ] Migration `0007_onboarding_state_and_events.py` (atenção aos defaults Postgres).
- [ ] CRUD em `docops/db/crud.py`: `get_or_create_state`, `apply_event`, `reset_state`.
- [ ] Router `docops/api/routes/onboarding.py` com os 3 endpoints (§5).
- [ ] Registrar router em `docops/api/app.py`.
- [ ] Feature flag: `is_feature_enabled("onboarding_enabled", default=True)` → se false, endpoints retornam 404.
- [ ] Testes: `tests/test_onboarding_api.py` cobrindo GET/POST/reset, idempotência, validação de step_id desconhecido, cálculo de tour_completed.

**Critério de done:** pytest verde; swagger mostra os endpoints; `POST /events { tour_reset }` limpa campos corretos.

### Fase 2 — Frontend: provider + checklist

- [ ] `web/src/onboarding/` com provider, hook, catalog (cópia do backend pra tipagem).
- [ ] Montar `OnboardingProvider` em `App.tsx` dentro do `CapabilitiesProvider`.
- [ ] Refatorar `OnboardingSteps` existente em `Dashboard.tsx:190` para `OnboardingChecklist` conectado ao state real.
- [ ] Checklist mostra: barra de progresso, passos concluídos com check, passos pendentes com CTA, botões "Pular tudo" e "Ocultar".
- [ ] Persistir `last_step_seen` ao clicar em CTA.
- [ ] Testes unitários (Vitest) do hook e do checklist.

**Critério de done:** usuário novo vê o checklist no Dashboard; concluir um passo manual reflete no backend; reload preserva estado.

### Fase 3 — Welcome modal
- [ ] `WelcomeModal.tsx` com 3 frames navegáveis, animação simples (framer-motion? ou CSS).
- [ ] Abrir modal automaticamente se `welcome_seen_at == null` e `tour_skipped_at == null`, após primeiro login (detectar via Auth + state).
- [ ] Botões "Começar tour" (dispara `tour_started` + `welcome_shown`) e "Explorar sozinho" (só `welcome_shown`).
- [ ] A11y: foco, ESC fecha, tab ordem.

**Critério de done:** primeiro login abre modal; segundo login não abre; fechar dispara evento correto.

### Fase 4 — Section intros

- [ ] `SectionIntro.tsx` renderizado no topo de cada page protegida.
- [ ] Para cada page (`Dashboard`, `Ingest`, `Chat`, `Artifacts`, `Docs`, `Notes`/`Tasks`/`Schedule` → `productivity`, `Flashcards`/`StudyPlan`/`ReadingKanban` → `study`, `Preferences`), integrar o componente.
- [ ] Botão "Entendi" / "Dispensar seção" / "Me mostra com tour" (placeholder até fase 5).

**Critério de done:** nenhum usuário novo entra em página sem ver o intro correspondente; skip de seção oculta o intro.

### Fase 5 — Auto-progression

- [ ] `useStepAutoComplete` hook.
- [ ] Plugar em: `Ingest.tsx` (upload), `Chat.tsx` (primeira resposta), `Artifacts.tsx`/`Chat.tsx` (save artifact), `Flashcards.tsx` (generate).
- [ ] Evitar duplicação: se passo já `completed_at != null`, hook não dispara POST.

**Critério de done:** fazer o fluxo inteiro real (upload → chat → artifact → flashcards) fecha 4 passos no checklist sem clique manual de "concluído".

### Fase 6 — Hotspot tour (seção por seção)

- [ ] Avaliar `react-joyride` vs implementação custom (30–80 linhas). Decisão documentada como ADR em `docs/onboarding/adr-001-hotspot-library.md`.
- [ ] Implementar para 3 seções críticas: **ingest**, **chat**, **artifacts**. Outras podem ficar só com SectionIntro.
- [ ] Cada seção tem 3–5 hotspots apontando para elementos chave via `data-tour-id`.

**Critério de done:** clicar "Me mostra com tour" na seção dispara sequência de tooltips.

### Fase 7 — Premium teasers

- [ ] Passos marcados `premium: true` no catálogo renderizam variante especial.
- [ ] Free tier vê: título + descrição genérica + badge "Pro" + CTA "Conhecer Pro" → dispara `upgrade_intent_from_onboarding`.
- [ ] Premium tier vê passo normal.
- [ ] Integrar com fluxo de upgrade existente (checar `CapabilitiesProvider`, `Artifacts.tsx` já tem lógica similar).

**Critério de done:** user free clicando no passo premium abre modal de upgrade, evento registrado em `user_onboarding_events`.

### Fase 8 — Re-abrir tour + Settings

- [ ] Card em `Preferences.tsx` com botões "Rever tutorial" e "Resetar progresso".
- [ ] "Rever" dispara `tour_reset`; "Resetar" chama `POST /reset` após confirmação.

### Fase 9 — Analytics + polish

- [ ] Dashboard interno (se existir) ou export CSV do funil: quantos chegam no welcome, quantos iniciam tour, quantos completam cada passo, onde abandonam.
- [ ] Reaproveitar infraestrutura de `premium_analytics_events` se possível, ou endpoint separado (`GET /api/analytics/onboarding/funnel`).
- [ ] Mobile pass: layout responsivo do welcome, checklist em drawer no mobile.
- [ ] Testes E2E (Playwright) do fluxo completo em `web/e2e/onboarding.spec.ts`.

## 9. Estratégia de testes

| Camada | O que testar | Ferramenta |
|---|---|---|
| Backend unit | CRUD, idempotência, cálculo de `tour_completed`, validação de step_id | pytest |
| Backend integration | Endpoints com Bearer token, feature flag off = 404, reset | pytest + TestClient |
| Frontend unit | Hook, provider, reducer do checklist | Vitest |
| Frontend component | WelcomeModal (a11y, navegação), SectionIntro (skip), Checklist (progress) | Testing Library |
| E2E | Fluxo novo usuário: login → welcome → tour → primeira ação real → checklist atualiza | Playwright |
| Visual | Screenshot dos estados principais | Playwright snapshot |

## 10. Métricas de sucesso

| Métrica | Baseline | Meta pós-lançamento |
|---|---|---|
| % novos users que completam ≥1 passo no d1 | — | ≥70% |
| % que completa fluxo mínimo (ingest → chat → artifact) | — | ≥40% |
| % que pula tudo no welcome | — | <20% |
| `upgrade_intent_from_onboarding` → conversão | — | instrumentar, sem meta v1 |

## 11. Riscos conhecidos

| Risco | Mitigação |
|---|---|
| Onboarding virar obstáculo chato | Princípios §2; skip em cada nível; testes com usuários reais antes de GA. |
| Auto-progression dispara duplicado | Idempotência backend + guard local no hook. |
| Catálogo diverge backend/frontend | `catalog.ts` gerado a partir do Python via script, rodado no CI. Fase 2 faz cópia manual; automação na Fase 9. |
| Schema_version bump quebra estado existente | Teste explícito: migration + seed de usuário com versão antiga + assert resposta com `schema_upgrade_available`. |
| Lista de passos crescer demais | Hard cap de 6 passos visíveis por vez no checklist; resto em "ver mais". |

## 12. Perguntas em aberto

1. **Gamificação?** Emblemas/streaks podem inflar engajamento mas desviam do foco. Decisão: **fora do v1**, reavaliar na Fase 9 se funil pedir.
2. **Onboarding rodar em conta Google login?** Sim — roda com qualquer auth. Não há diferença.
3. **Localização PT/EN no mesmo catálogo?** Não v1. Campo `i18n_key` no catálogo planejado para v2.
4. **Deve existir "tour interativo" no mobile?** Mobile v1: welcome + checklist + section intros. Hotspots (Fase 6) desabilitados no mobile inicialmente.

## 13. Próximos passos imediatos

1. Você revisa esta spec e comenta o que quer mudar.
2. Após OK, abrimos a **Fase 1** (backend scaffold). Cada fase = commit específico pra ser fácil reverter.
3. PR final apenas depois da Fase 5 (valor mínimo: auto-progression funcionando), Fases 6–9 podem ir em PRs posteriores.
