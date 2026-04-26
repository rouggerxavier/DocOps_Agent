"""Static catalog describing the onboarding tour.

The catalog is the single source of truth for sections, steps and event
vocabulary. It is embedded in the `GET /api/onboarding/state` response so the
frontend does not need a separate request to render the tour.

Design notes (see `docs/onboarding/spec.md` for the full spec):

- `ONBOARDING_SCHEMA_VERSION` bumps when the shape of sections/steps
  meaningfully changes. The backend stores the version last seen by each user
  and reports `schema_upgrade_available` when it lags behind.
- Steps flagged with `premium=True` are optional for tour completion: a free
  user can finish the tour without them. Completing a premium step still
  counts if the user chooses to.
- `completion_mode` is metadata for the frontend:
  - "manual": user clicks "Entendi" to mark the step done.
  - "auto":   the step is auto-completed from a hook (e.g. first upload).
- `next_hint` suggests the natural next step, letting the frontend chain
  sections together ("depois disso, vá para Chat…").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


ONBOARDING_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class OnboardingStep:
    id: str
    section_id: str
    title: str
    description: str
    premium: bool = False
    completion_mode: str = "manual"  # "manual" | "auto"
    next_hint: tuple[str, str, str] | None = None  # (section_id, step_id, route)


@dataclass(frozen=True)
class OnboardingSection:
    id: str
    title: str
    icon: str
    route: str
    steps: tuple[OnboardingStep, ...] = field(default_factory=tuple)


# Event vocabulary. Any value outside this set is rejected with 400.
EVENT_TYPES: frozenset[str] = frozenset(
    {
        "welcome_shown",
        "tour_started",
        "step_seen",
        "step_completed",
        "section_skipped",
        "tour_skipped",
        "tour_completed",  # reserved for backend-derived events; clients may also emit
        "tour_reset",
        "upgrade_intent_from_onboarding",
    }
)


# Events whose state mutation is idempotent: replaying them must not move the
# recorded timestamp forward and must not produce a duplicate telemetry row.
IDEMPOTENT_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "welcome_shown",
        "tour_started",
        "step_completed",
        "section_skipped",
    }
)


# ── Catalog v1 ────────────────────────────────────────────────────────────────

SECTIONS: tuple[OnboardingSection, ...] = (
    OnboardingSection(
        id="dashboard",
        title="Dashboard",
        icon="layout",
        route="/dashboard",
        steps=(
            OnboardingStep(
                id="dashboard.explore",
                section_id="dashboard",
                title="Entenda seu painel",
                description=(
                    "Visão geral das suas conversas, documentos importados, "
                    "artefatos criados e recomendações."
                ),
                completion_mode="manual",
                next_hint=("ingest", "ingest.first_upload", "/ingest"),
            ),
        ),
    ),
    OnboardingSection(
        id="ingest",
        title="Inserção",
        icon="upload",
        route="/ingest",
        steps=(
            OnboardingStep(
                id="ingest.types_overview",
                section_id="ingest",
                title="4 formas de trazer conteúdo",
                description=(
                    "Arquivo (PDF/MD/TXT), URL de artigo, foto com OCR e clip "
                    "compartilhado do celular."
                ),
                completion_mode="manual",
            ),
            OnboardingStep(
                id="ingest.first_upload",
                section_id="ingest",
                title="Insira seu primeiro documento",
                description=(
                    "Arraste um arquivo aqui ou clique em escolher. Aceitamos "
                    "PDF, Markdown e TXT."
                ),
                completion_mode="auto",
                next_hint=("chat", "chat.first_question", "/chat"),
            ),
        ),
    ),
    OnboardingSection(
        id="chat",
        title="Chat",
        icon="message-square",
        route="/chat",
        steps=(
            OnboardingStep(
                id="chat.first_question",
                section_id="chat",
                title="Faça sua primeira pergunta",
                description=(
                    "O chat responde a partir dos seus documentos, com citações "
                    "numeradas em cada trecho usado."
                ),
                completion_mode="auto",
                next_hint=("chat", "chat.grounding_modes", "/chat"),
            ),
            OnboardingStep(
                id="chat.grounding_modes",
                section_id="chat",
                title="Modos de resposta",
                description=(
                    "Equilibrado para estudar e Estrito para pesquisa — cada modo "
                    "tem impacto diferente na confiança da resposta."
                ),
                completion_mode="manual",
                next_hint=("artifacts", "artifacts.first_save", "/artifacts"),
            ),
            OnboardingStep(
                id="chat.memory",
                section_id="chat",
                title="Memória ativa",
                description=(
                    "Personaliza tom, profundidade e rotina das respostas com base "
                    "nas suas preferências."
                ),
                premium=True,
                completion_mode="manual",
            ),
        ),
    ),
    OnboardingSection(
        id="artifacts",
        title="Artefatos",
        icon="file-text",
        route="/artifacts",
        steps=(
            OnboardingStep(
                id="artifacts.first_save",
                section_id="artifacts",
                title="Transforme chat em artefato",
                description=(
                    "Salve uma resposta como resumo, checklist ou nota estruturada "
                    "para consultar depois."
                ),
                completion_mode="auto",
                next_hint=("docs", "docs.library", "/docs"),
            ),
            OnboardingStep(
                id="artifacts.premium_templates",
                section_id="artifacts",
                title="Templates avançados",
                description=(
                    "Exam pack e deep dossier — formatos estruturados para provas "
                    "e pesquisas profundas."
                ),
                premium=True,
                completion_mode="manual",
            ),
        ),
    ),
    OnboardingSection(
        id="docs",
        title="Documentos",
        icon="folder",
        route="/docs",
        steps=(
            OnboardingStep(
                id="docs.library",
                section_id="docs",
                title="Sua biblioteca",
                description=(
                    "Lista completa dos documentos inseridos. Filtre, marque "
                    "status de leitura e remova quando quiser."
                ),
                completion_mode="manual",
                next_hint=("productivity", "productivity.notes_tasks", "/tasks"),
            ),
        ),
    ),
    OnboardingSection(
        id="productivity",
        title="Produtividade",
        icon="clipboard",
        route="/tasks",
        steps=(
            OnboardingStep(
                id="productivity.notes_tasks",
                section_id="productivity",
                title="Anote e organize",
                description=(
                    "Notas rápidas, tarefas com checklist e um calendário para "
                    "lembretes e rotina de estudos."
                ),
                completion_mode="manual",
                next_hint=("study", "study.flashcards", "/flashcards"),
            ),
        ),
    ),
    OnboardingSection(
        id="study",
        title="Estudo",
        icon="graduation-cap",
        route="/flashcards",
        steps=(
            OnboardingStep(
                id="study.flashcards",
                section_id="study",
                title="Gere flashcards automáticos",
                description=(
                    "A partir dos seus documentos criamos decks com revisão "
                    "espaçada (SRS)."
                ),
                completion_mode="auto",
                next_hint=("study", "study.plan", "/studyplan"),
            ),
            OnboardingStep(
                id="study.plan",
                section_id="study",
                title="Plano de estudos",
                description=(
                    "Cria um plano adaptado ao seu prazo com análise de lacunas "
                    "do conteúdo."
                ),
                completion_mode="manual",
                next_hint=("study", "study.kanban", "/kanban"),
            ),
            OnboardingStep(
                id="study.kanban",
                section_id="study",
                title="Kanban de leitura",
                description=(
                    "Visualização em board para organizar o que está por ler, "
                    "lendo e concluído."
                ),
                completion_mode="manual",
            ),
        ),
    ),
    OnboardingSection(
        id="settings",
        title="Configurações",
        icon="sliders",
        route="/settings",
        steps=(
            OnboardingStep(
                id="settings.personalization",
                section_id="settings",
                title="Personalize respostas",
                description=(
                    "Ajuste tom, profundidade e rigor padrão das respostas para "
                    "combinar com seu estilo."
                ),
                completion_mode="manual",
            ),
        ),
    ),
)


# ── Indexes and helpers ───────────────────────────────────────────────────────


def catalog_sections() -> tuple[OnboardingSection, ...]:
    """Return the full catalog. Returns the module-level tuple; do not mutate."""
    return SECTIONS


def _build_step_index() -> dict[str, OnboardingStep]:
    index: dict[str, OnboardingStep] = {}
    for section in SECTIONS:
        for step in section.steps:
            if step.id in index:
                raise RuntimeError(f"Duplicate step id in catalog: {step.id}")
            index[step.id] = step
    return index


def _build_section_index() -> dict[str, OnboardingSection]:
    index: dict[str, OnboardingSection] = {}
    for section in SECTIONS:
        if section.id in index:
            raise RuntimeError(f"Duplicate section id in catalog: {section.id}")
        index[section.id] = section
    return index


_STEP_INDEX = _build_step_index()
_SECTION_INDEX = _build_section_index()


def get_step(step_id: str) -> OnboardingStep | None:
    return _STEP_INDEX.get(step_id)


def get_section(section_id: str) -> OnboardingSection | None:
    return _SECTION_INDEX.get(section_id)


def is_known_step(step_id: str | None) -> bool:
    return bool(step_id) and step_id in _STEP_INDEX


def is_known_section(section_id: str | None) -> bool:
    return bool(section_id) and section_id in _SECTION_INDEX


def is_known_event_type(event_type: str | None) -> bool:
    return bool(event_type) and event_type in EVENT_TYPES


def total_step_count() -> int:
    return sum(len(section.steps) for section in SECTIONS)


def required_step_ids(section_skips: Iterable[str] | None = None) -> list[str]:
    """Steps that must be completed for `tour_completed_at` to be set.

    Premium steps and steps inside a skipped section are excluded.
    """
    skipped = set(section_skips or ())
    ids: list[str] = []
    for section in SECTIONS:
        if section.id in skipped:
            continue
        for step in section.steps:
            if step.premium:
                continue
            ids.append(step.id)
    return ids
