"""Orquestrador inteligente de ações cross-module.

Substitui e expande o action_router com parser LLM capaz de:
  1. Detectar intents complexos e cascades multi-step
  2. Extrair entidades (tópico, prazo, documento, deck)
  3. Executar sequências de ações nos módulos existentes

Cascades implementados:
  cascade_study_event    — "tenho prova de X na sexta" → tarefa + lembretes de estudo
  cascade_doc_review     — "revise X com flashcards" → deck + agendamento de revisões SRS
  cascade_task_deadline  — "entregar Y na quinta" → tarefa com due_date + lembrete
  schedule_fc_reviews    — "agende revisões dos flashcards de X" → lembretes SRS

Fluxo no chat.py:
  orchestrator.maybe_orchestrate() → dict (answer + intent) | None
  → None → calendar_assistant → RAG graph
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from docops.logging import get_logger

logger = get_logger("docops.services.orchestrator")

_TASK_ACTION_KEYWORDS = (
    "tarefa",
    "tarefas",
    "to-do",
    "todo",
    "afazer",
    "afazeres",
    "pendencia",
    "pendência",
    "pendencias",
    "pendências",
)
_FLASHCARD_ACTION_KEYWORDS = (
    "flashcard",
    "flashcards",
    "card",
    "cards",
    "cartao",
    "cartoes",
    "revisao",
    "revisao espaçada",
    "revisao espaciada",
)
_FLASHCARD_BATCH_KEYWORDS = (
    "cada documento",
    "todos os documentos",
    "todos os docs",
    "todos os arquivos",
    "aba documentos",
    "lista de documentos",
    "em lote",
    "por documento",
)
_FLASHCARD_COMMAND_KEYWORDS = (
    "crie",
    "criar",
    "gere",
    "gerar",
    "faça",
    "faca",
    "monte",
    "produza",
    "prepare",
)
_FLASHCARD_CONFIRMATION_WORDS = {
    "sim",
    "pode",
    "pode sim",
    "ok",
    "okay",
    "confirmo",
    "confirmar",
    "todos",
    "todos os documentos",
    "cada documento",
    "usar todos",
}
_FLASHCARD_NEGATION_WORDS = {
    "nao",
    "não",
    "negativo",
    "nenhum",
    "nenhuma",
    "cancelar",
    "cancela",
}
_DEEP_SUMMARY_HINTS = (
    "aprofundado",
    "aprofundada",
    "profundo",
    "profunda",
    "detalhado",
    "detalhada",
    "secao por secao",
    "seção por seção",
    "analitico",
    "analítico",
    "completo",
    "completa",
)

_pending_study_plans: dict[int, dict] = {}
_pending_flashcard_batches: dict[int, dict] = {}

# ---------------------------------------------------------------------------
# Prompt do parser LLM
# ---------------------------------------------------------------------------

_PARSE_TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

_PARSER_PROMPT = f"""\
Você é um parser de intenções para um assistente pessoal. Hoje é {_PARSE_TODAY}.

Analise a mensagem do usuário e retorne APENAS um JSON válido (sem markdown, sem texto extra).

Intents possíveis:
- "cascade_study_event"  → usuário menciona prova, exame, avaliação com prazo/data
- "cascade_study_plan"   → usuário quer criar um plano de estudos para um documento/tema
- "cascade_doc_review"   → usuário quer revisar/estudar um documento específico com flashcards
- "cascade_task_deadline"→ usuário menciona entrega, deadline, prazo de um trabalho/projeto
- "schedule_fc_reviews"  → usuário quer agendar revisões de flashcards já existentes
- "create_task"          → criar tarefa simples sem prazo específico (afazer, to-do, pendência)
- "list_tasks"           → listar tarefas pendentes
- "flashcard_hint"       → pede flashcards de um documento sem cascade
- "create_flashcards_batch" → criar flashcards para um ou mais documentos, incluindo "todos os documentos"
- "cascade_create_note"  → usuário quer criar/salvar uma ANOTAÇÃO ou NOTA textual (explicitamente menciona "nota", "anotação")
- "cascade_create_summary" → usuário quer fazer um resumo de um documento específico
- "clarification_needed"  → comando ambíguo que precisa de confirmação antes de executar
- "calendar"             → qualquer coisa relacionada a calendário, agenda, lembrete, rotina, cronograma, horário fixo, blocos semanais, compromisso, evento
- "rag"                  → pergunta sobre documentos, dúvida, QA — deve ir pro RAG

Regras PRIORITÁRIAS (em ordem de prioridade):
1. CALENDÁRIO tem prioridade máxima sobre notas e tarefas. Use "calendar" se qualquer uma dessas condições for verdadeira:
   - Menciona "calendário", "agenda", "cronograma", "rotina", "horário fixo", "bloco", "recorrente"
   - Menciona "lembrete" (mesmo sem mencionar "calendário" explicitamente) → "calendar"
   - Menciona dias da semana com horários (ex: "segunda das 8 às 12", "de segunda a sexta")
   - Menciona horários fixos com frequência (ex: "todo dia", "toda semana", "de manhã")
   - Pede para "organizar minha semana", "criar minha rotina", "montar meu cronograma"
   - O usuário corrigiu explicitamente dizendo "não é nota", "não é tarefa", "é no calendário", "é na agenda"

2. Use "cascade_create_note" SOMENTE se o usuário mencionar EXPLICITAMENTE "nota", "anotação", "anotar" — e NÃO houver menção a calendário/lembrete/rotina/horário.

3. Use "create_task" SOMENTE se o usuário mencionar EXPLICITAMENTE "tarefa", "to-do", "afazer", "pendência" — e NÃO houver menção a calendário/lembrete/rotina/horário.

4. Se a mensagem for uma pergunta factual ou pedir informação de documento → "rag"
5. Se mencionar prova/exame/teste + data → "cascade_study_event"
6. Se mencionar "plano de estudos", "cronograma de estudos", "me ajuda a estudar [doc]", "estudar [doc] até [data]" → "cascade_study_plan"
7. Se mencionar entrega/prazo/deadline de projeto/trabalho + data → "cascade_task_deadline"
8. Se mencionar "resumo de", "resumir [doc]", "faz um resumo", "sumarize" → "cascade_create_summary"
9. Se mencionar criar/gerar flashcards para vários documentos, "todos os documentos" ou "cada documento" → "create_flashcards_batch"

Exemplos para calibração:
- "lembrete no calendário para as 14h" → "calendar"
- "criar um lembrete" → "calendar"
- "criar minha rotina" → "calendar"
- "segunda a sexta das 8 às 12 estágio" → "calendar"
- "organizar minha semana" → "calendar"
- "não é nas notas, é no calendário" → "calendar"
- "anota isso: revisar capítulo 3" → "cascade_create_note"
- "criar tarefa: entregar trabalho amanhã" → "create_task"  (sem deadline específico → "create_task"; com deadline → "cascade_task_deadline")
- "tenho prova de física sexta" → "cascade_study_event"
- "quero 10 flashcards para cada documento" → "create_flashcards_batch"

- Datas relativas: "amanhã"=+1d, "depois de amanhã"=+2d, "semana que vem"=+7d, "próxima semana"=+7d
- Se não houver data clara, deadline_iso = null
- doc_hint: nome ou parte do nome do documento mencionado, null se não mencionado
- topic: assunto principal (ex: "física", "cálculo diferencial"), null se não mencionado
- task_title: título limpo da tarefa (começa com verbo), null se não aplicável
- deck_hint: parte do nome do deck/documento para flashcards
- hours_per_day: horas por dia de estudo mencionadas (número float), null se não mencionado
- content: conteúdo ou texto da nota que o usuário quer salvar, null se não especificado
- all_docs: true quando a instrução inclui "todos os documentos", "cada documento", "todos os docs" ou equivalente
- doc_names: lista de nomes de documentos explicitamente mencionados quando o usuário quer algo em lote
- needs_confirmation: true quando a instrução pede uma ação, mas faltam documentos-alvo ou a intenção ainda está ambígua

Formato de resposta:
{{
  "intent": "<intent>",
  "entities": {{
    "topic": "<string ou null>",
    "task_title": "<string ou null>",
    "doc_hint": "<string ou null>",
    "deck_hint": "<string ou null>",
    "deadline_iso": "<YYYY-MM-DD ou null>",
    "deadline_label": "<descrição legível da data ou null>",
    "hours_per_day": "<float ou null>",
    "content": "<string ou null>",
    "all_docs": "<bool ou null>",
    "doc_names": ["<string>", "..."],
    "needs_confirmation": "<bool ou null>"
  }}
}}

{{HISTORY_BLOCK}}{{ACTIVE_CONTEXT_BLOCK}}Mensagem do usuário: {{MESSAGE}}
"""


# ---------------------------------------------------------------------------
# Funções auxiliares de data
# ---------------------------------------------------------------------------

_MONTH_MAP = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}


def _parse_date_from_text(text: str) -> datetime | None:
    """Tenta parsear datas relativas comuns em português."""
    now = datetime.now(timezone.utc)
    t = text.lower()

    # "DD de Mês" ou "dia DD de Mês" (ex: "10 de abril", "dia 5 de maio")
    m = re.search(
        r"(?:dia\s+)?(\d{1,2})\s+de\s+(janeiro|fevereiro|mar[çc]o|abril|maio|junho|"
        r"julho|agosto|setembro|outubro|novembro|dezembro)(?:\s+de\s+(\d{4}))?",
        t,
    )
    if m:
        day = int(m.group(1))
        month_raw = m.group(2).replace("março", "março").replace("marco", "março")
        month = _MONTH_MAP.get(month_raw)
        year = int(m.group(3)) if m.group(3) else now.year
        if month:
            try:
                candidate = datetime(year, month, day, tzinfo=timezone.utc)
                # Se a data já passou neste ano, avança para o próximo
                if candidate < now and not m.group(3):
                    candidate = datetime(year + 1, month, day, tzinfo=timezone.utc)
                return candidate
            except ValueError:
                pass

    # "dia DD" sem mês (ex: "até dia 08", "dia 8") → assume mês atual, ou próximo se já passou
    m_day_only = re.search(r"(?:até\s+)?dia\s+(\d{1,2})(?!\s+de\s+\w)", t)
    if m_day_only:
        day = int(m_day_only.group(1))
        if 1 <= day <= 31:
            try:
                candidate = datetime(now.year, now.month, day, tzinfo=timezone.utc)
                if candidate < now:
                    # Avança para o próximo mês
                    next_month = now.month % 12 + 1
                    next_year = now.year + (1 if now.month == 12 else 0)
                    candidate = datetime(next_year, next_month, day, tzinfo=timezone.utc)
                return candidate
            except ValueError:
                pass

    # "DD/MM" ou "DD/MM/YYYY"
    m2 = re.search(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?", t)
    if m2:
        day, month = int(m2.group(1)), int(m2.group(2))
        year = int(m2.group(3)) if m2.group(3) else now.year
        try:
            candidate = datetime(year, month, day, tzinfo=timezone.utc)
            if candidate < now and not m2.group(3):
                candidate = datetime(year + 1, month, day, tzinfo=timezone.utc)
            return candidate
        except ValueError:
            pass

    patterns = [
        (r"hoje", 0),
        (r"amanh[ãa]", 1),
        (r"depois de amanh[ãa]", 2),
        (r"em (\d+) dias?", None),
        (r"daqui a (\d+) dias?", None),
        (r"próxima semana|semana que vem|próximas? semana", 7),
        (r"em (\d+) semanas?", None),
        (r"daqui a (\d+) semanas?", None),
        (r"próximas? (\d+) dias?", None),
        (r"sexta(?:-feira)?", None),
        (r"quinta(?:-feira)?", None),
        (r"quarta(?:-feira)?", None),
        (r"terça(?:-feira)?", None),
        (r"segunda(?:-feira)?", None),
        (r"sábado", None),
        (r"domingo", None),
    ]

    weekday_map = {
        "segunda": 0, "terça": 1, "quarta": 2, "quinta": 3,
        "sexta": 4, "sábado": 5, "domingo": 6,
    }

    for pattern, delta in patterns:
        m3 = re.search(pattern, t)
        if m3:
            if delta is not None:
                return now + timedelta(days=delta)
            if m3.lastindex and m3.lastindex >= 1:
                try:
                    val = int(m3.group(1))
                    # semanas → dias
                    mult = 7 if "semana" in pattern else 1
                    return now + timedelta(days=val * mult)
                except (ValueError, IndexError):
                    pass
            for name, wd in weekday_map.items():
                if name in pattern:
                    days_ahead = (wd - now.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    return now + timedelta(days=days_ahead)

    # ISO date YYYY-MM-DD
    iso = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if iso:
        try:
            return datetime.strptime(iso.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


def _reminder_times_for_deadline(deadline: datetime) -> list[tuple[str, datetime]]:
    """Retorna lembretes SRS para um prazo: D-3, D-1 e D-day manhã."""
    now = datetime.now(timezone.utc)
    slots = []
    for label, delta_days, hour in [("Revisão inicial", -3, 19), ("Véspera", -1, 19), ("Dia da prova", 0, 7)]:
        t = deadline.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=delta_days)
        if t > now + timedelta(hours=1):
            slots.append((label, t))
    return slots


def _srs_review_times(from_dt: datetime) -> list[tuple[str, datetime]]:
    """Revisões SRS clássicas: +1d, +3d, +7d a partir de hoje."""
    now = from_dt
    return [
        ("1ª revisão", now + timedelta(days=1)),
        ("2ª revisão", now + timedelta(days=3)),
        ("3ª revisão", now + timedelta(days=7)),
    ]


def _normalize_text(text: str) -> str:
    normalized = text.casefold().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _has_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = _normalize_text(text)
    return any(keyword in normalized for keyword in keywords)


def _looks_like_task_command(message: str) -> bool:
    normalized = _normalize_text(message)
    return _has_any_keyword(normalized, _TASK_ACTION_KEYWORDS)


def _looks_like_flashcard_command(message: str) -> bool:
    normalized = _normalize_text(message)
    return _has_any_keyword(normalized, _FLASHCARD_ACTION_KEYWORDS)


def _looks_like_flashcard_batch_request(message: str) -> bool:
    normalized = _normalize_text(message)
    return _has_any_keyword(normalized, _FLASHCARD_BATCH_KEYWORDS)


def _looks_like_flashcard_confirmation(message: str) -> bool:
    normalized = _normalize_text(message)
    if normalized in _FLASHCARD_CONFIRMATION_WORDS:
        return True
    return any(word in normalized for word in _FLASHCARD_CONFIRMATION_WORDS)


def _looks_like_flashcard_negation(message: str) -> bool:
    normalized = _normalize_text(message)
    if normalized in _FLASHCARD_NEGATION_WORDS:
        return True
    return any(word in normalized for word in _FLASHCARD_NEGATION_WORDS)


def _looks_like_deep_summary_request(message: str) -> bool:
    normalized = _normalize_text(message)
    return any(word in normalized for word in _DEEP_SUMMARY_HINTS)


def _extract_explicit_doc_names(message: str, docs: list) -> list[str]:
    normalized = _normalize_text(message)
    matched: list[str] = []
    for doc in docs:
        file_name = getattr(doc, "file_name", "") or ""
        short_name = _normalize_text(file_name)
        if short_name and (short_name in normalized or normalized in short_name):
            matched.append(file_name)
    return matched


def _active_doc_names(active_context: dict | None) -> list[str]:
    if not active_context:
        return []
    return [str(value).strip() for value in (active_context.get("active_doc_names") or []) if str(value).strip()]


def _active_doc_ids(active_context: dict | None) -> list[str]:
    if not active_context:
        return []
    return [str(value).strip() for value in (active_context.get("active_doc_ids") or []) if str(value).strip()]


def _build_active_context_block(active_context: dict | None) -> str:
    if not active_context:
        return ""

    lines: list[str] = []
    doc_names = _active_doc_names(active_context)
    if doc_names:
        lines.append("Contexto ativo da conversa:")
        lines.append(f"- Documentos ativos: {', '.join(doc_names[:5])}")

    if active_context.get("active_deck_title"):
        lines.append(f"- Deck ativo: {active_context['active_deck_title']}")
    if active_context.get("active_task_title"):
        lines.append(f"- Tarefa ativa: {active_context['active_task_title']}")
    if active_context.get("active_note_title"):
        lines.append(f"- Nota ativa: {active_context['active_note_title']}")
    if active_context.get("last_action"):
        lines.append(f"- Última ação: {active_context['last_action']}")
    if active_context.get("last_card_count"):
        lines.append(f"- Última quantidade de cards: {active_context['last_card_count']}")

    mix = active_context.get("last_difficulty_mix") or {}
    if isinstance(mix, dict) and any(mix.get(key) for key in ("facil", "media", "dificil")):
        lines.append(
            "- Última distribuição de dificuldade: "
            f"{int(mix.get('facil', 0))} fáceis, "
            f"{int(mix.get('media', 0))} médias, "
            f"{int(mix.get('dificil', 0))} difíceis"
        )

    return ("\n".join(lines) + "\n\n") if lines else ""


def _apply_active_context_to_entities(intent: str, entities: dict, active_context: dict | None, message: str) -> dict:
    merged = dict(entities or {})
    doc_names = _active_doc_names(active_context)
    doc_ids = _active_doc_ids(active_context)

    if intent in {
        "create_flashcards_batch",
        "flashcard_hint",
        "cascade_doc_review",
        "cascade_study_plan",
        "cascade_create_summary",
    }:
        if not merged.get("doc_names") and doc_names:
            merged["doc_names"] = list(doc_names)
        if not merged.get("doc_hint") and not merged.get("deck_hint") and len(doc_names) == 1:
            merged["doc_hint"] = doc_names[0]
            merged["deck_hint"] = doc_names[0]

        normalized = _normalize_text(message)
        if (
            _looks_like_flashcard_command(message)
            and re.search(r"\b(mais|outros|outras|novos)\b", normalized)
            and not merged.get("num_cards")
            and active_context
            and active_context.get("last_card_count")
        ):
            merged["num_cards"] = active_context.get("last_card_count")

        if (
            _looks_like_flashcard_command(message)
            and not merged.get("difficulty_custom")
            and active_context
            and active_context.get("last_difficulty_mix")
        ):
            merged["difficulty_custom"] = active_context.get("last_difficulty_mix")
            merged["difficulty_mode"] = "custom"

    if not merged.get("doc_ids") and doc_ids:
        merged["doc_ids"] = list(doc_ids)

    return merged


def _build_flashcard_confirmation_answer(entities: dict, docs: list) -> dict:
    doc_hint = entities.get("doc_hint") or entities.get("deck_hint") or ""
    if docs:
        sample = "\n".join(f"- {doc.file_name}" for doc in docs[:5])
        return {
            "answer": (
                "Posso gerar flashcards, mas preciso saber se você quer um documento específico "
                "ou todos os documentos da aba Documentos.\n\n"
                f"Documentos disponíveis:\n{sample}\n\n"
                "Responda com o nome do documento, ou diga `todos os documentos`."
            ),
            "intent": "create_flashcards_batch",
            "needs_confirmation": True,
            "entities": {
                "doc_hint": doc_hint,
                "all_docs": False,
                "doc_names": [],
            },
        }
    return {
        "answer": (
            "Posso gerar flashcards, mas primeiro você precisa inserir documentos na aba Documentos."
        ),
        "intent": "create_flashcards_batch",
        "needs_confirmation": True,
        "entities": {
            "doc_hint": doc_hint,
            "all_docs": False,
            "doc_names": [],
        },
    }


def _build_ambiguous_command_answer(message: str, entities: dict, docs: list | None = None) -> dict:
    if _looks_like_flashcard_command(message):
        return _build_flashcard_confirmation_answer(entities, docs or [])

    return {
        "answer": (
            "Não entendi com segurança se isso é uma tarefa, uma pergunta ou outra ação. "
            "Se quiser criar uma tarefa, diga algo como `criar tarefa: ...`. "
            "Se quiser flashcards, diga o documento ou `todos os documentos`."
        ),
        "intent": "clarification_needed",
        "needs_confirmation": True,
    }


def _queue_flashcard_batch_confirmation(user_id: int, message: str, entities: dict) -> None:
    _pending_flashcard_batches[user_id] = {
        "message": message,
        "entities": dict(entities or {}),
    }


# ---------------------------------------------------------------------------
# Parser LLM
# ---------------------------------------------------------------------------

def _llm_parse(
    message: str,
    history: list[dict] | None = None,
    active_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Chama o LLM barato para parsear a intenção. Retorna dict ou None se erro."""
    try:
        from docops.config import config
        from google import genai

        client = genai.Client(api_key=config.gemini_api_key)
        model = getattr(config, "gemini_model_cheap", None) or config.gemini_model

        history_block = ""
        if history:
            lines = ["Histórico recente da conversa (use para resolver referências anafóricas):"]
            for turn in history[-8:]:
                role_label = "Usuário" if turn.get("role") == "user" else "Assistente"
                content = str(turn.get("content", ""))[:300]
                lines.append(f"{role_label}: {content}")
            history_block = "\n".join(lines) + "\n\n"

        active_context_block = _build_active_context_block(active_context)
        prompt = (
            _PARSER_PROMPT
            .replace("{MESSAGE}", message)
            .replace("{HISTORY_BLOCK}", history_block)
            .replace("{ACTIVE_CONTEXT_BLOCK}", active_context_block)
        )
        logger.info("Orchestrator: chamando LLM parser (model=%s)", model)
        response = client.models.generate_content(model=model, contents=prompt)
        raw = response.text.strip()
        logger.info("Orchestrator: LLM raw=%r", raw[:200])
        # Extrai JSON mesmo se vier com markdown ao redor
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            logger.info("Orchestrator: nenhum JSON encontrado na resposta do LLM")
            return None
        parsed = json.loads(match.group(0))
        logger.info("Orchestrator: parsed=%s", parsed)
        return parsed
    except Exception as exc:
        logger.info("Orchestrator: LLM parser falhou — %s: %s", type(exc).__name__, exc)
        return None


def _invoke_llm_parse(
    message: str,
    history: list[dict] | None = None,
    active_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Call _llm_parse with compatibility for legacy monkeypatch signatures."""
    try:
        return _llm_parse(message, history=history, active_context=active_context)
    except TypeError:
        try:
            return _llm_parse(message, history=history)
        except TypeError:
            try:
                return _llm_parse(message)
            except TypeError:
                return None


# ---------------------------------------------------------------------------
# Executores de cascade
# ---------------------------------------------------------------------------

def _exec_cascade_study_event(entities: dict, user_id: int, db: Session) -> dict:
    """Prova/exame próximo → tarefa de estudo + lembretes escalonados."""
    from docops.db import crud

    topic = entities.get("topic") or "Estudo"
    deadline_iso = entities.get("deadline_iso")
    deadline_label = entities.get("deadline_label") or deadline_iso or "prazo"

    deadline_dt = None
    if deadline_iso:
        try:
            deadline_dt = datetime.strptime(deadline_iso, "%Y-%m-%d").replace(
                hour=9, minute=0, tzinfo=timezone.utc
            )
        except ValueError:
            pass

    # 1. Criar tarefa
    task_title = f"Estudar {topic}"
    try:
        task = crud.create_task_record(
            db,
            user_id=user_id,
            title=task_title,
            priority="high",
            due_date=deadline_dt,
        )
        task_line = f'✅ Tarefa criada: **"{task.title}"** (alta prioridade)'
    except Exception as exc:
        logger.error("Falha ao criar tarefa no cascade_study_event: %s", exc)
        task_line = f"⚠️ Não foi possível criar a tarefa."

    # 2. Criar lembretes de estudo
    reminder_lines = []
    if deadline_dt:
        reminders = _reminder_times_for_deadline(deadline_dt)
        for label, dt in reminders:
            try:
                r = crud.create_reminder_record(
                    db,
                    user_id=user_id,
                    title=f"📚 {label} — {topic}",
                    starts_at=dt,
                    note=f"Revisão programada automaticamente para: {topic}",
                )
                reminder_lines.append(f"📅 {label}: {dt.strftime('%d/%m %H:%M')}")
            except Exception as exc:
                logger.error("Falha ao criar lembrete: %s", exc)
                reminder_lines.append(f"⚠️ Lembrete '{label}' não criado.")

    answer_parts = [
        f"🎯 Entendido! Organizei o estudo de **{topic}** para **{deadline_label}**:\n",
        task_line,
    ]
    if reminder_lines:
        answer_parts.append("\n**Lembretes criados no calendário:**")
        answer_parts.extend(reminder_lines)

    answer_parts.append("\nVeja seus [Lembretes →](/schedule) e [Tarefas →](/tasks)")

    return {
        "answer": "\n".join(answer_parts),
        "intent": "cascade_study_event",
        "active_context": {
            "active_task_id": getattr(locals().get("task", None), "id", None),
            "active_task_title": task_title,
            "active_intent": "cascade_study_event",
            "last_action": "cascade_study_event",
        },
    }


def _exec_cascade_doc_review(entities: dict, user_id: int, db: Session) -> dict:
    """Documento → deck de flashcards + agendamento de revisões SRS."""
    from docops.db import crud

    doc_hint = entities.get("doc_hint") or ""
    docs = crud.list_documents_for_user(db, user_id)

    if not docs:
        return {
            "answer": "Você ainda não inseriu documentos. Adicione na [Inserção](/ingest) primeiro.",
            "intent": "cascade_doc_review",
        }

    # Localiza documento por dica
    hint_lower = doc_hint.lower()
    matched_doc = next(
        (d for d in docs if hint_lower and (hint_lower in d.file_name.lower() or d.file_name.lower() in hint_lower)),
        docs[0] if len(docs) == 1 else None,
    )

    if not matched_doc:
        doc_list = "\n".join(f"- {d.file_name}" for d in docs[:5])
        return {
            "answer": (
                f'Não encontrei documento com "{doc_hint}". Documentos disponíveis:\n{doc_list}\n\n'
                "Tente ser mais específico ou use o [Smart Digest](/docs)."
            ),
            "intent": "cascade_doc_review",
        }

    # Gera flashcards
    deck_id = None
    deck_line = ""
    try:
        from docops.services.flashcard_generation import generate_cards
        cards = generate_cards(
            doc_name=matched_doc.file_name,
            doc_id=matched_doc.doc_id,
            user_id=user_id,
            num_cards=10,
            difficulty_mode="any",
        )
        deck = crud.create_flashcard_deck(
            db,
            user_id=user_id,
            source_doc=matched_doc.file_name,
            title=f"Flashcards — {matched_doc.file_name}",
            cards=cards,
        )
        deck_id = deck.id
        deck_line = f"🃏 Deck criado: **{len(cards)} flashcards** de _{matched_doc.file_name}_"
    except Exception as exc:
        logger.error("Falha ao gerar flashcards no cascade_doc_review: %s", exc)
        deck_line = "⚠️ Não foi possível gerar flashcards agora. Tente pelo [menu de Documentos](/docs)."

    # Agenda revisões SRS
    reminder_lines = []
    if deck_id:
        now = datetime.now(timezone.utc)
        for label, dt in _srs_review_times(now):
            try:
                crud.create_reminder_record(
                    db,
                    user_id=user_id,
                    title=f"🔁 {label} — flashcards de {matched_doc.file_name}",
                    starts_at=dt.replace(hour=19, minute=0, second=0),
                    note=f"Revisão espaçada automática. Deck ID: {deck_id}",
                )
                reminder_lines.append(f"📅 {label}: {dt.strftime('%d/%m')}")
            except Exception as exc:
                logger.error("Falha ao criar lembrete SRS: %s", exc)

    answer_parts = [
        f"📚 Tudo pronto para revisar **{matched_doc.file_name}**!\n",
        deck_line,
    ]
    if reminder_lines:
        answer_parts.append("\n**Revisões SRS agendadas no calendário:**")
        answer_parts.extend(reminder_lines)

    answer_parts.append(f"\n[Estudar os flashcards →](/flashcards)")

    return {
        "answer": "\n".join(answer_parts),
        "intent": "cascade_doc_review",
        "active_context": {
            "active_doc_ids": [str(getattr(matched_doc, "doc_id", "") or "")] if str(getattr(matched_doc, "doc_id", "") or "").strip() else [],
            "active_doc_names": [matched_doc.file_name],
            "active_deck_id": deck_id,
            "active_deck_title": f"Flashcards — {matched_doc.file_name}" if deck_id else None,
            "active_intent": "cascade_doc_review",
            "last_action": "cascade_doc_review",
            "last_card_count": 10 if deck_id else None,
        },
    }


def _exec_cascade_task_deadline(entities: dict, user_id: int, db: Session) -> dict:
    """Entrega/projeto com prazo → tarefa com due_date + lembrete D-1."""
    from docops.db import crud

    task_title = entities.get("task_title") or entities.get("topic") or "Entrega"
    deadline_iso = entities.get("deadline_iso")
    deadline_label = entities.get("deadline_label") or deadline_iso or "prazo definido"

    deadline_dt = None
    if deadline_iso:
        try:
            deadline_dt = datetime.strptime(deadline_iso, "%Y-%m-%d").replace(
                hour=23, minute=59, tzinfo=timezone.utc
            )
        except ValueError:
            pass

    # Criar tarefa
    try:
        task = crud.create_task_record(
            db,
            user_id=user_id,
            title=task_title,
            priority="high",
            due_date=deadline_dt,
        )
        task_line = f'✅ Tarefa: **"{task.title}"** — prazo: {deadline_label}'
    except Exception as exc:
        logger.error("Falha ao criar tarefa deadline: %s", exc)
        task_line = "⚠️ Não foi possível criar a tarefa."

    # Lembrete D-1
    reminder_line = ""
    if deadline_dt:
        reminder_dt = (deadline_dt - timedelta(days=1)).replace(hour=9, minute=0)
        now = datetime.now(timezone.utc)
        if reminder_dt > now:
            try:
                crud.create_reminder_record(
                    db,
                    user_id=user_id,
                    title=f"⚠️ Amanhã é a entrega: {task_title}",
                    starts_at=reminder_dt,
                    note="Lembrete automático criado pelo orquestrador.",
                )
                reminder_line = f"📅 Lembrete criado para {reminder_dt.strftime('%d/%m')} às 09:00"
            except Exception as exc:
                logger.error("Falha ao criar lembrete de entrega: %s", exc)

    answer_parts = [f"📋 Registrei sua entrega:\n", task_line]
    if reminder_line:
        answer_parts.append(reminder_line)
    answer_parts.append("\n[Ver Tarefas →](/tasks) · [Calendário →](/schedule)")

    return {
        "answer": "\n".join(answer_parts),
        "intent": "cascade_task_deadline",
        "active_context": {
            "active_task_id": getattr(locals().get("task", None), "id", None),
            "active_task_title": task_title,
            "active_intent": "cascade_task_deadline",
            "last_action": "cascade_task_deadline",
        },
    }


def _exec_schedule_fc_reviews(entities: dict, user_id: int, db: Session) -> dict:
    """Agenda revisões SRS para um deck de flashcards existente."""
    from docops.db import crud

    deck_hint = entities.get("deck_hint") or entities.get("doc_hint") or ""
    decks = crud.list_flashcard_decks_for_user(db, user_id)

    if not decks:
        return {
            "answer": "Você ainda não tem decks de flashcards. Crie um na [página de Documentos](/docs) usando o Smart Digest.",
            "intent": "schedule_fc_reviews",
        }

    hint_lower = deck_hint.lower()
    matched = next(
        (d for d in decks if hint_lower and (hint_lower in d.title.lower() or hint_lower in (d.source_doc or "").lower())),
        decks[0] if len(decks) == 1 else None,
    )

    if not matched:
        deck_list = "\n".join(f"- {d.title}" for d in decks[:5])
        return {
            "answer": f"Não encontrei o deck. Seus decks:\n{deck_list}\n\nSeja mais específico.",
            "intent": "schedule_fc_reviews",
        }

    now = datetime.now(timezone.utc)
    reminder_lines = []
    for label, dt in _srs_review_times(now):
        try:
            crud.create_reminder_record(
                db,
                user_id=user_id,
                title=f"🔁 {label} — {matched.title}",
                starts_at=dt.replace(hour=19, minute=0, second=0),
                note=f"Revisão espaçada. Deck: {matched.title}",
            )
            reminder_lines.append(f"📅 {label}: {dt.strftime('%d/%m')} às 19h")
        except Exception as exc:
            logger.error("Falha ao criar lembrete SRS: %s", exc)

    answer = (
        f"🔁 Revisões agendadas para **{matched.title}**:\n\n"
        + "\n".join(reminder_lines)
        + "\n\n[Ver Calendário →](/schedule)"
    )
    return {
        "answer": answer,
        "intent": "schedule_fc_reviews",
        "active_context": {
            "active_deck_id": getattr(matched, "id", None),
            "active_deck_title": matched.title,
            "active_doc_names": [matched.source_doc] if getattr(matched, "source_doc", None) else [],
            "active_intent": "schedule_fc_reviews",
            "last_action": "schedule_fc_reviews",
        },
    }


def _resolve_flashcard_batch_docs(
    entities: dict,
    message: str,
    docs: list,
    active_context: dict | None = None,
) -> tuple[list, bool]:
    all_docs = bool(entities.get("all_docs")) or _looks_like_flashcard_batch_request(message)
    doc_names = entities.get("doc_names") or []
    doc_hint = entities.get("doc_hint") or entities.get("deck_hint") or ""

    explicit_from_message = _extract_explicit_doc_names(message, docs)
    if explicit_from_message:
        matched = [
            doc
            for doc in docs
            if getattr(doc, "file_name", "") in explicit_from_message
        ]
        return matched, False

    if all_docs:
        return list(docs), True

    explicit_names = [str(name).strip() for name in doc_names if str(name).strip()]
    if explicit_names:
        normalized = {_normalize_text(name) for name in explicit_names}
        matched = [
            doc
            for doc in docs
            if _normalize_text(getattr(doc, "file_name", "")) in normalized
            or any(
                hint in _normalize_text(getattr(doc, "file_name", ""))
                for hint in normalized
            )
        ]
        return matched, False

    context_doc_ids = set(_active_doc_ids(active_context))
    if context_doc_ids:
        matched = [
            doc
            for doc in docs
            if str(getattr(doc, "doc_id", "") or "").strip() in context_doc_ids
        ]
        if matched:
            return matched, False

    context_doc_names = _active_doc_names(active_context)
    if context_doc_names:
        normalized = {_normalize_text(name) for name in context_doc_names}
        matched = [
            doc
            for doc in docs
            if _normalize_text(getattr(doc, "file_name", "")) in normalized
            or any(
                hint in _normalize_text(getattr(doc, "file_name", ""))
                for hint in normalized
            )
        ]
        if matched:
            return matched, False

    if doc_hint:
        hint_lower = _normalize_text(str(doc_hint))
        matched = [
            doc
            for doc in docs
            if hint_lower in _normalize_text(getattr(doc, "file_name", ""))
            or _normalize_text(getattr(doc, "file_name", "")) in hint_lower
        ]
        return matched, False

    return [], False


def _exec_create_flashcards_batch(
    entities: dict,
    user_id: int,
    db: Session,
    message: str,
    active_context: dict | None = None,
) -> dict:
    from docops.db import crud
    from docops.services.flashcard_generation import generate_cards

    docs = crud.list_documents_for_user(db, user_id)
    if not docs:
        return _build_flashcard_confirmation_answer(entities, docs)

    target_docs, is_all_docs = _resolve_flashcard_batch_docs(entities, message, docs, active_context=active_context)
    if not target_docs:
        _pending_flashcard_batches[user_id] = {"entities": entities, "message": message}
        return _build_flashcard_confirmation_answer(entities, docs)

    num_cards = entities.get("num_cards") or entities.get("total_cards") or 10
    try:
        num_cards = int(num_cards)
    except (TypeError, ValueError):
        num_cards = 10

    difficulty_mode = str(entities.get("difficulty_mode") or "any")
    difficulty_custom = entities.get("difficulty_custom")
    content_filter = str(entities.get("content_filter") or "").strip()

    created: list[str] = []
    failed: list[str] = []

    for doc in target_docs:
        try:
            cards = generate_cards(
                doc_name=doc.file_name,
                doc_id=doc.doc_id,
                user_id=user_id,
                num_cards=num_cards,
                content_filter=content_filter,
                difficulty_mode=difficulty_mode,
                difficulty_custom=difficulty_custom,
            )
            deck = crud.create_flashcard_deck(
                db,
                user_id=user_id,
                title=f"Flashcards - {doc.file_name}",
                source_doc=doc.file_name,
                cards=cards,
            )
            created.append(f"{deck.title} ({len(cards)} cards)")
        except Exception as exc:
            logger.error("Falha ao gerar flashcards em lote para %s: %s", doc.file_name, exc)
            failed.append(doc.file_name)

    if not created and failed:
        return {
            "answer": (
                "Não consegui gerar flashcards em lote agora. Tente novamente pela página de Flashcards "
                "ou reduza o escopo para um documento só."
            ),
            "intent": "create_flashcards_batch",
        }

    summary_lines = [f"✅ Gerei {len(created)} deck(s) de flashcards."]
    if is_all_docs:
        summary_lines.append("Escopo: todos os documentos disponíveis.")
    if created:
        summary_lines.append("Decks criados:")
        summary_lines.extend(f"- {item}" for item in created[:8])
    if failed:
        summary_lines.append("")
        summary_lines.append(f"⚠️ Falha em {len(failed)} documento(s): " + ", ".join(failed[:5]))
    summary_lines.append("\n[Ver Flashcards →](/flashcards)")

    _pending_flashcard_batches.pop(user_id, None)
    return {
        "answer": "\n".join(summary_lines),
        "intent": "create_flashcards_batch",
        "entities": {
            "doc_names": [doc.file_name for doc in target_docs],
            "all_docs": is_all_docs,
            "num_cards": num_cards,
        },
        "active_context": {
            "active_doc_ids": [str(getattr(doc, "doc_id", "") or "") for doc in target_docs if str(getattr(doc, "doc_id", "") or "").strip()],
            "active_doc_names": [doc.file_name for doc in target_docs],
            "active_intent": "create_flashcards_batch",
            "last_action": "create_flashcards_batch",
            "last_card_count": num_cards,
            "last_difficulty_mix": difficulty_custom if isinstance(difficulty_custom, dict) else None,
        },
    }


def _handle_pending_flashcard_batch(
    message: str,
    user_id: int,
    db: Session,
    active_context: dict | None = None,
) -> dict | None:
    pending = _pending_flashcard_batches.get(user_id)
    if not pending:
        return None

    normalized = _normalize_text(message)
    if _looks_like_flashcard_negation(normalized):
        _pending_flashcard_batches.pop(user_id, None)
        return {
            "answer": "Tudo bem. Não vou gerar esse lote agora. Se quiser, me diga `todos os documentos` ou o nome do documento depois.",
            "intent": "create_flashcards_batch",
        }

    docs = None
    try:
        from docops.db import crud
        docs = crud.list_documents_for_user(db, user_id)
    except Exception:
        docs = []

    explicit_names = _extract_explicit_doc_names(message, docs or [])
    if explicit_names:
        entities = dict(pending.get("entities") or {})
        entities["doc_names"] = explicit_names
        entities["all_docs"] = False
        return _exec_create_flashcards_batch(
            entities,
            user_id,
            db,
            pending.get("message", message),
            active_context=active_context,
        )

    if _looks_like_flashcard_batch_request(message):
        entities = dict(pending.get("entities") or {})
        entities["all_docs"] = True
        return _exec_create_flashcards_batch(
            entities,
            user_id,
            db,
            pending.get("message", message),
            active_context=active_context,
        )

    if _looks_like_flashcard_confirmation(normalized):
        return _build_flashcard_confirmation_answer(pending.get("entities") or {}, docs or [])

    return None


# ---------------------------------------------------------------------------
# Cascade: Plano de Estudos (multi-turn)
# ---------------------------------------------------------------------------

def _extract_followup_info(message: str) -> dict:
    """Extrai horas/dia e prazo de uma resposta de follow-up simples."""
    result: dict = {}

    # Horas: "2h", "2 horas", "1.5h por dia", "3 horas diárias"
    h_match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(?:h(?:oras?)?|hrs?)(?:\s*(?:por|ao|\/)\s*dia)?",
        message,
        re.IGNORECASE,
    )
    if h_match:
        try:
            result["hours_per_day"] = float(h_match.group(1).replace(",", "."))
        except ValueError:
            pass

    # Prazo: usa o parser de datas existente
    dt = _parse_date_from_text(message)
    if dt:
        result["deadline_iso"] = dt.strftime("%Y-%m-%d")
        result["deadline_label"] = dt.strftime("%d/%m/%Y")

    return result


def _exec_cascade_study_plan(entities: dict, user_id: int, db: Session) -> dict:
    """Cria plano de estudos completo: tarefas + sessões no calendário + flashcards."""
    from docops.db import crud
    from datetime import date as _date

    doc_hint = entities.get("doc_hint") or entities.get("topic") or ""
    hours_raw = entities.get("hours_per_day")
    deadline_iso = entities.get("deadline_iso")

    # Resolve horas (pode vir como string "2.0" do LLM)
    hours_per_day: float | None = None
    if hours_raw is not None:
        try:
            hours_per_day = float(hours_raw)
        except (ValueError, TypeError):
            pass

    # Verifica se faltam informações → pergunta ao usuário
    missing = []
    if not hours_per_day:
        missing.append("quantas horas por dia você pode dedicar (ex: 2h)")
    if not deadline_iso:
        missing.append("até quando quer concluir o estudo (ex: 20/04, em 2 semanas)")

    if missing:
        # Armazena o que já temos para o próximo turn
        _pending_study_plans[user_id] = {
            "entities": entities,
            "missing": list(missing),
        }
        questions = " e ".join(missing)
        doc_part = f" de **{doc_hint}**" if doc_hint else ""
        return {
            "answer": (
                f"Para criar seu plano de estudos{doc_part}, preciso saber: "
                f"{questions}?"
            ),
            "intent": "cascade_study_plan_ask",
            "active_context": {
                "active_doc_names": [doc_hint] if doc_hint else [],
                "active_intent": "cascade_study_plan_ask",
                "last_action": "cascade_study_plan_ask",
            },
        }

    # Temos tudo — localiza documento
    docs = crud.list_documents_for_user(db, user_id)
    if not docs:
        _pending_study_plans.pop(user_id, None)
        return {
            "answer": "Você ainda não inseriu documentos. Adicione na [Inserção](/ingest) primeiro.",
            "intent": "cascade_study_plan",
        }

    hint_lower = doc_hint.lower()
    matched_doc = next(
        (d for d in docs if hint_lower and (
            hint_lower in d.file_name.lower() or d.file_name.lower() in hint_lower
        )),
        docs[0] if len(docs) == 1 else None,
    )

    if not matched_doc:
        doc_list = "\n".join(f"- {d.file_name}" for d in docs[:5])
        _pending_study_plans.pop(user_id, None)
        return {
            "answer": (
                f'Não encontrei documento com "{doc_hint}". Disponíveis:\n{doc_list}\n\n'
                "Tente ser mais específico."
            ),
            "intent": "cascade_study_plan",
        }

    try:
        deadline = _date.fromisoformat(deadline_iso)
    except (ValueError, TypeError):
        _pending_study_plans.pop(user_id, None)
        return {
            "answer": "Não consegui interpretar a data. Tente novamente com formato DD/MM ou 'em X dias'.",
            "intent": "cascade_study_plan",
        }

    if deadline <= _date.today():
        _pending_study_plans.pop(user_id, None)
        return {
            "answer": "O prazo precisa ser uma data futura. Tente novamente.",
            "intent": "cascade_study_plan",
        }

    # Executa o gerador
    _pending_study_plans.pop(user_id, None)
    try:
        from docops.services.study_plan_generator import generate_study_plan
        result = generate_study_plan(
            doc_name=matched_doc.file_name,
            doc_id=matched_doc.doc_id,
            user_id=user_id,
            hours_per_day=hours_per_day,
            deadline=deadline,
            db=db,
            generate_flashcards=True,
            num_cards=12,
        )
    except Exception as exc:
        logger.error("Falha ao gerar plano de estudos: %s", exc)
        return {
            "answer": "Ocorreu um erro ao gerar o plano de estudos. Tente pela [página de Plano de Estudos](/study-plan).",
            "intent": "cascade_study_plan",
        }

    # Salva plano no banco
    try:
        from docops.db import crud as _crud
        plan_record = _crud.create_study_plan_record(
            db,
            user_id=user_id,
            titulo=result["titulo"],
            doc_name=matched_doc.file_name,
            plan_text=result["plan_text"],
            tasks_created=result["tasks_created"],
            reminders_created=result["reminders_created"],
            sessions_count=result["sessions_count"],
            deck_id=result["deck_id"],
            hours_per_day=hours_per_day,
            deadline_date=deadline_iso,
        )
        logger.info("Cascade study plan: plano salvo (id=%d)", plan_record.id)
    except Exception as exc:
        logger.warning("Falha ao salvar plano de estudos no cascade: %s", exc)

    sessions = result["sessions_count"]
    tasks = result["tasks_created"]
    deck_note = " + flashcards criados" if result["deck_id"] else ""
    conflicts = result.get("conflicts", [])

    answer = (
        f"📚 Plano de estudos criado para **{matched_doc.file_name}**!\n\n"
        f"- ✅ **{tasks} tarefas** por tópico criadas\n"
        f"- 📅 **{sessions} sessões de estudo** no calendário ({hours_per_day:.0f}h/dia){deck_note}\n"
        f"- Prazo: **{deadline.strftime('%d/%m/%Y')}**\n\n"
        f"[Ver Plano →](/study-plan) · [Ver Tarefas →](/tasks) · [Ver Calendário →](/schedule)"
    )
    if result["deck_id"]:
        answer += " · [Flashcards →](/flashcards)"

    if conflicts:
        conflict_items = "\n".join(
            f"  - {c['date']}: sessão {c['session_time']} conflita com **{c['conflicting_with']}** ({c['conflicting_time']})"
            for c in conflicts[:3]
        )
        answer += f"\n\n⚠️ **{len(conflicts)} conflito(s) de horário detectado(s):**\n{conflict_items}"
        answer += "\nVerifique seu [Calendário →](/schedule) para ajustar se necessário."

    return {
        "answer": answer,
        "intent": "cascade_study_plan",
        "active_context": {
            "active_doc_ids": [str(getattr(matched_doc, "doc_id", "") or "")] if str(getattr(matched_doc, "doc_id", "") or "").strip() else [],
            "active_doc_names": [matched_doc.file_name],
            "active_deck_id": result.get("deck_id"),
            "active_intent": "cascade_study_plan",
            "last_action": "cascade_study_plan",
            "last_card_count": 12 if result.get("deck_id") else None,
        },
    }


# ---------------------------------------------------------------------------
# Cascade: Criar Nota
# ---------------------------------------------------------------------------

def _exec_cascade_create_note(entities: dict, user_id: int, db: Session, original_message: str) -> dict:
    """Cria uma nota com o conteúdo fornecido pelo usuário."""
    from docops.db import crud

    topic = entities.get("topic") or entities.get("task_title") or "Nota"
    content_raw = entities.get("content") or ""

    # Se o usuário não forneceu conteúdo, usa a mensagem original como corpo
    if not content_raw:
        content_raw = original_message

    title = f"Nota: {topic}"
    try:
        note = crud.create_note_record(
            db,
            user_id=user_id,
            title=title,
            content=content_raw,
        )
        return {
            "answer": (
                f"📝 Nota criada: **{note.title}**\n\n"
                f"[Ver Notas →](/notes)"
            ),
            "intent": "cascade_create_note",
            "active_context": {
                "active_note_id": getattr(note, "id", None),
                "active_note_title": note.title,
                "active_intent": "cascade_create_note",
                "last_action": "cascade_create_note",
            },
        }
    except Exception as exc:
        logger.error("Falha ao criar nota: %s", exc)
        return {
            "answer": "Não foi possível criar a nota. Tente pela [página de Notas](/notes).",
            "intent": "cascade_create_note",
        }


def _exec_cascade_create_summary(entities: dict, user_id: int, db: Session) -> dict:
    """Orienta o usuário a criar resumo aprofundado via página de Artefatos."""
    doc_hint = entities.get("doc_hint") or ""

    if doc_hint:
        return {
            "answer": (
                f"📄 Para um **resumo aprofundado** de **{doc_hint}**, recomendo usar "
                f"[Artefatos →](/artifacts) e clicar em **Resumir Documento** > "
                f"**Resumo Aprofundado**.\n"
                f"Se quiser, **Resumo Breve** eu já faço direto aqui no chat.\n\n"
                f"Assim o conteúdo fica completo e salvo automaticamente em seus artefatos."
            ),
            "intent": "cascade_create_summary",
            "active_context": {
                "active_doc_names": [doc_hint],
                "active_intent": "cascade_create_summary",
                "last_action": "cascade_create_summary",
            },
        }
    return {
        "answer": (
            "📄 Para resumo aprofundado, recomendo usar [Artefatos →](/artifacts) "
            "e clicar em **Resumir Documento** > **Resumo Aprofundado**.\n"
            "Se quiser, **Resumo Breve** eu já faço direto aqui no chat."
        ),
        "intent": "cascade_create_summary",
        "active_context": {
            "active_intent": "cascade_create_summary",
            "last_action": "cascade_create_summary",
        },
    }


# ---------------------------------------------------------------------------
# Entry point principal
# ---------------------------------------------------------------------------

# Intents simples que delegam para o action_router existente (sem cascade)
_SIMPLE_INTENTS = {"create_task", "list_tasks", "flashcard_hint"}
# Intents que devem cair no RAG ou calendar_assistant
_PASSTHROUGH_INTENTS = {"rag", "calendar"}


def maybe_orchestrate(
    message: str,
    user_id: int,
    db: Session,
    history: list[dict] | None = None,
    session_id: str | None = None,
    active_context: dict | None = None,
) -> dict | None:  # noqa: C901
    """Tenta orquestrar a mensagem com parser LLM + cascades.

    Returns:
        dict com 'answer' e 'intent' se a mensagem foi tratada,
        None para cair no fluxo seguinte (calendar_assistant → RAG).
    """
    # Mensagens muito curtas raramente são cascades — pula parser
    if len(message.strip()) < 10:
        return None

    # ── Early-exit: calendário/update-reminder têm prioridade sobre TUDO ──
    # Isso inclui pending study plans — não deixar que o LLM ou pending state
    # intercepte mensagens claramente direcionadas ao calendar_assistant.
    _CALENDAR_PRIORITY_RE = re.compile(
        # Correção explícita de destino
        r"(?:não\s+(?:é|era|foi)\s+(?:nas?\s+)?(?:nota[s]?|tarefa[s]?|anotação|to.?do))"
        r"|(?:(?:é|quero)\s+(?:no\s+)?(?:calendário|agenda))"
        r"|(?:coloca\s+(?:no\s+)?(?:calendário|agenda))"
        # Update de lembrete: "mude/altere/muda/modifique + (o lembrete|para as Xh|horário)"
        r"|(?:(?:mud[ea]|alter[ea]|modifiqu[ea]|atualiz[ea])\s+(?:o\s+)?(?:lembrete|horário|a\s+hora))"
        r"|(?:(?:mud[ea]|alter[ea]|modifiqu[ea]|atualiz[ea]).*(?:para\s+as?\s+\d{1,2}h?))"
        # Lembrete com referência direta
        r"|(?:lembrete.*(?:para|de)\s+(?:as?\s+)?\d{1,2}(?:h|:\d{2}))"
        r"|(?:criar?\s+(?:um\s+)?lembrete)"
        r"|(?:adicionar?\s+(?:um\s+)?lembrete)",
        re.IGNORECASE,
    )
    if _CALENDAR_PRIORITY_RE.search(message):
        logger.info("Orchestrator: mensagem de calendário/lembrete → pass-through imediato")
        return None  # Deixa o calendar_assistant processar

    pending_flashcards = _handle_pending_flashcard_batch(message, user_id, db, active_context=active_context)
    if pending_flashcards:
        return pending_flashcards

    # ── Verifica se há um plano de estudos pendente para este usuário ──────
    if user_id in _pending_study_plans:
        pending = _pending_study_plans[user_id]
        followup = _extract_followup_info(message)
        if not followup:
            # Tenta extrair via LLM com contexto do pending (ex: "até dia 08" sem horas)
            llm_result = _invoke_llm_parse(message, history=history, active_context=active_context)
            if llm_result and llm_result.get("intent") in ("cascade_study_plan", "rag", "create_task", "cascade_task_deadline"):
                ents = llm_result.get("entities", {})
                if ents.get("deadline_iso"):
                    followup["deadline_iso"] = ents["deadline_iso"]
                    followup["deadline_label"] = ents.get("deadline_label") or ents["deadline_iso"]
                if ents.get("hours_per_day"):
                    followup["hours_per_day"] = ents["hours_per_day"]
        if followup:
            # Mescla o que o usuário respondeu com as entidades já coletadas
            merged_entities = {**pending["entities"], **followup}
            logger.info("Orchestrator: follow-up study_plan para user=%d, merged=%s", user_id, merged_entities)
            return _exec_cascade_study_plan(merged_entities, user_id, db)
        # Resposta verdadeiramente não parseável — cancela o pending e trata normalmente
        _pending_study_plans.pop(user_id, None)

    parsed = _invoke_llm_parse(message, history=history, active_context=active_context)
    if not parsed:
        logger.debug("Parser LLM não retornou JSON válido.")
        return None

    intent = parsed.get("intent", "rag")
    entities = _apply_active_context_to_entities(
        intent,
        parsed.get("entities", {}),
        active_context,
        message,
    )

    docs_for_user: list = []
    try:
        from docops.db import crud
        docs_for_user = crud.list_documents_for_user(db, user_id)
    except Exception:
        docs_for_user = []

    if intent == "create_task" and _looks_like_flashcard_command(message):
        if _looks_like_flashcard_batch_request(message) or entities.get("all_docs") or entities.get("doc_names") or entities.get("doc_hint") or entities.get("deck_hint"):
            intent = "create_flashcards_batch"
        else:
            _queue_flashcard_batch_confirmation(user_id, message, entities)
            return _build_ambiguous_command_answer(message, entities, docs_for_user)

    if intent == "flashcard_hint" and _looks_like_flashcard_command(message):
        if _looks_like_flashcard_batch_request(message) or entities.get("all_docs") or entities.get("doc_names") or entities.get("doc_hint") or entities.get("deck_hint"):
            intent = "create_flashcards_batch"
        else:
            _queue_flashcard_batch_confirmation(user_id, message, entities)
            return _build_ambiguous_command_answer(message, entities, docs_for_user)

    if intent == "create_task" and not _looks_like_task_command(message):
        if _looks_like_flashcard_command(message):
            _queue_flashcard_batch_confirmation(user_id, message, entities)
        return _build_ambiguous_command_answer(message, entities, docs_for_user)

    if intent == "clarification_needed":
        question = entities.get("question") or "Posso te ajudar, mas preciso de mais detalhes."
        return {
            "answer": question,
            "intent": "clarification_needed",
        }

    entities = _apply_active_context_to_entities(intent, entities, active_context, message)
    logger.info("Orchestrator: intent=%s entities=%s", intent, entities)

    # Cascades multi-step
    if intent == "cascade_study_event":
        return _exec_cascade_study_event(entities, user_id, db)

    if intent == "cascade_study_plan":
        return _exec_cascade_study_plan(entities, user_id, db)

    if intent == "cascade_doc_review":
        return _exec_cascade_doc_review(entities, user_id, db)

    if intent == "cascade_task_deadline":
        return _exec_cascade_task_deadline(entities, user_id, db)

    if intent == "schedule_fc_reviews":
        return _exec_schedule_fc_reviews(entities, user_id, db)

    if intent == "cascade_create_note":
        return _exec_cascade_create_note(entities, user_id, db, message)

    if intent == "cascade_create_summary":
        if _looks_like_deep_summary_request(message):
            return _exec_cascade_create_summary(entities, user_id, db)
        logger.info("Orchestrator: resumo breve/genérico -> pass-through para RAG chat")
        return None

    if intent == "create_flashcards_batch":
        return _exec_create_flashcards_batch(entities, user_id, db, message, active_context=active_context)

    # Ações simples — delega pro action_router que já funciona bem com regex
    if intent in _SIMPLE_INTENTS:
        from docops.services.action_router import maybe_answer_action_query
        result = maybe_answer_action_query(message, user_id, db)
        if result:
            if result.get("intent") == "create_task":
                result["active_context"] = {
                    "active_task_title": entities.get("task_title") or message.strip(),
                    "active_intent": "create_task",
                    "last_action": "create_task",
                }
            elif result.get("intent") == "list_tasks":
                result["active_context"] = {
                    "active_intent": "list_tasks",
                    "last_action": "list_tasks",
                }
            return result
        # Se regex não pegou, tenta executar baseado nas entidades do LLM
        if intent == "create_task":
            if _looks_like_flashcard_command(message):
                if _looks_like_flashcard_batch_request(message) or entities.get("all_docs") or entities.get("doc_names") or entities.get("doc_hint") or entities.get("deck_hint"):
                    return _exec_create_flashcards_batch(entities, user_id, db, message, active_context=active_context)
                return _build_ambiguous_command_answer(message, entities, docs_for_user)
            title = entities.get("task_title") or message.strip()
            from docops.services.action_router import _handle_create_task
            result = _handle_create_task(title, user_id, db)
            result["active_context"] = {
                "active_task_title": title,
                "active_intent": "create_task",
                "last_action": "create_task",
            }
            return result
        if intent == "list_tasks":
            from docops.services.action_router import _handle_list_tasks
            return _handle_list_tasks(user_id, db)
        if intent == "flashcard_hint":
            if _looks_like_flashcard_batch_request(message) or entities.get("all_docs") or entities.get("doc_names"):
                return _exec_create_flashcards_batch(entities, user_id, db, message, active_context=active_context)
            hint = entities.get("doc_hint") or entities.get("deck_hint") or ""
            from docops.services.action_router import _handle_flashcard_hint
            result = _handle_flashcard_hint(hint, user_id, db)
            result["active_context"] = {
                "active_doc_names": [hint] if hint else [],
                "active_intent": "flashcard_hint",
                "last_action": "flashcard_hint",
            }
            return result

    # intent == "rag" ou "calendar" → retorna None para cair no fluxo normal
    # "calendar" passa para o calendar_assistant (Stage 2) que tem a lógica correta
    if intent == "calendar":
        logger.info("Orchestrator: intent=calendar → pass-through para calendar_assistant")
        return None

    return None

